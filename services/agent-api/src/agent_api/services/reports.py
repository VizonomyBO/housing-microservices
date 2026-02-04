import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import jinja2
import markdown
import weasyprint
from shared_data_layer.repositories.documents import DocumentRepository
from shared_data_layer.schemas.countries import COUNTRY_NAME_BY_ALPHA3
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.agent.runner import LangGraphRunner
from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.schemas import ChatMessagePayload, ResponseMode
from agent_api.models.chat import ChatRequestContext
from agent_api.report_cache import get_cached_report, upload_cached_report
from agent_api.services.conversations import ConversationService
from agent_api.settings import Settings

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def _simplify_country_name(country_name: str) -> str:
    """Simplify official ISO country names for report readability.
    
    Examples:
        "Bolivia, Plurinational State of" → "Bolivia"
        "United States of America" → "United States"
    """
    return country_name.split(',')[0].strip()


def _map_chunk_citations_to_documents(
    markdown_content: str,
    citations: list[dict],
    document_index: dict[str, int]
) -> tuple[str, dict[str, int]]:
    """Map chunk-based citations [c1], [c2] to document-based citations [1], [2].
    
    Deduplicates consecutive citations so [1][1][1] becomes [1] and [1][2][1] becomes [1][2].
    
    Args:
        markdown_content: Text with [c1], [c2], etc. citations
        citations: List of citation dicts with canonical_name and chunk info
        document_index: Mapping of document_name -> citation number (updated in place)
    
    Returns:
        Tuple of (updated_content, updated_document_index)
    
    Example:
        Input text: "Housing markets are complex[c1][c2]. Policies matter[c3]."
        Where c1, c2 are from doc A and c3 is from doc B
        Output text: "Housing markets are complex[1]. Policies matter[2]."
    """
    # Build mapping: c1 -> document_name -> [citation_number]
    chunk_to_doc_citation = {}
    
    for idx, citation in enumerate(citations, start=1):
        doc_name = citation.get("canonical_name") or citation.get("doc_id", "Unknown")
        chunk_citation = f"c{idx}"
        
        # Assign document number if not already assigned
        if doc_name not in document_index:
            document_index[doc_name] = len(document_index) + 1
        
        doc_citation_num = document_index[doc_name]
        chunk_to_doc_citation[chunk_citation] = doc_citation_num
    
    # Replace [c1] -> [1], [c2] -> [2], etc.
    for chunk_cit, doc_num in chunk_to_doc_citation.items():
        markdown_content = markdown_content.replace(f"[{chunk_cit}]", f"[{doc_num}]")
    
    # Deduplicate citations in groups: [1][1][1] -> [1], [1][2][1] -> [1][2]
    # Handles all separator formats: [10],[10], [10]-[10], [10].[10]
    # Preserves sentence punctuation AND spacing: [1][3]. Together, [10][1], [1].
    def deduplicate_citation_group(match):
        group = match.group(0)
        # Extract all citation numbers from any format
        citation_nums = re.findall(r'\[(\d+)\]', group)
        
        # Deduplicate while preserving order: ['1', '2', '1'] -> ['1', '2']
        seen = set()
        unique_citations = []
        for num in citation_nums:
            if num not in seen:
                unique_citations.append(num)
                seen.add(num)
        
        # Check for trailing punctuation + space after last citation
        trailing = ''
        after_citations = group[group.rfind(']')+1:]  # Everything after last ]
        
        # If there's punctuation followed by space/end, preserve it
        punct_match = re.match(r'^[,.\-\s]*([.,;!?])(\s*)', after_citations)
        if punct_match:
            # Preserve if it's sentence punctuation (followed by space or end of string)
            if punct_match.group(2) or not re.match(r'^\d', after_citations[len(punct_match.group()):]):
                trailing = punct_match.group(1) + punct_match.group(2)
        
        # Rebuild: clean citations + trailing punctuation/space
        return ''.join(f'[{num}]' for num in unique_citations) + trailing
    
    # Match citation groups with any separators, stop before letters
    markdown_content = re.sub(r'\[\d+\](?:[,.\-\s]*\[\d+\])*[,.\-\s]*(?=[A-Z]|[a-z]|$)', deduplicate_citation_group, markdown_content)
    
    return markdown_content, document_index


def _get_section_prompts(country_name: str) -> list[dict[str, str]]:
    """Generate section prompts with country name injected and strict evidence requirements."""
    # Base instruction for all sections to prevent hallucination
    base_instruction = (
        f"First, retrieve relevant documents about {country_name}'s housing sector. "
        f"CRITICAL: ONLY use information explicitly stated in the retrieved documents. "
        f"If documents mention '{country_name}' specifically, write about {country_name}. "
        f"If documents only mention 'Latin America', 'LAC', or regional patterns, write 'in Latin America' or 'regionally'. "
        f"If documents only mention global patterns, write 'globally' or 'internationally'. "
        f"Do NOT infer {country_name}-specific statistics, institutions, programs, or policies unless explicitly stated in the documents. "
        f"Do NOT provide statistics without document support. "
        f"If evidence is limited, state 'regional evidence suggests...' or 'global studies show...'. "
    )
    
    return [
        {
            "title": "1. Executive Summary",
            "prompt": f"{base_instruction}Then write an Executive Summary for {country_name}'s housing market based on available evidence. Summarize market conditions, main constraints, and high-potential opportunities using only document-supported claims. Outline emerging trends and policy levers. Clearly distinguish between {country_name}-specific findings and regional/global patterns.",
        },
        {
            "title": "2. Introduction of Purpose and Scope",
            "prompt": f"{base_instruction}Then write the Introduction of Purpose and Scope. State that the report diagnoses housing market patterns using evidence from retrieved documents. Describe the analytical framework and document types. If documents are regional/global rather than {country_name}-specific, state that clearly.",
        },
        {
            "title": "3. National and Regional Context",
            "prompt": f"{base_instruction}Then write the National and Regional Context. ONLY include {country_name}-specific data if explicitly stated in documents. If documents discuss Latin America or regional patterns, frame findings as regional context. Do NOT invent city names, demographic statistics, or GDP figures not in the documents.",
        },
        {
            "title": "4. Housing Sector within the Economy",
            "prompt": f"{base_instruction}Then write the 'Housing Sector within the Economy' section. If documents provide {country_name} GDP/employment data, use it. Otherwise, describe regional or global patterns and explicitly label them as such (e.g., 'in Latin American countries' or 'globally, housing sectors contribute...'). Do NOT estimate {country_name} figures without document support.",
        },
        {
            "title": "5. Institutional and Legal Framework",
            "prompt": f"{base_instruction}Then write the Institutional and Legal Framework section. ONLY describe {country_name} institutions/laws if explicitly mentioned in documents. If documents discuss regional patterns, write 'in Latin America' or 'regional institutional frameworks typically...'. Do NOT name specific {country_name} agencies or programs unless cited in documents.",
        },
        {
            "title": "6. Housing Supply",
            "prompt": f"{base_instruction}Then write the Housing Supply section. Base analysis on document evidence. If documents discuss land access patterns regionally, state that. If {country_name} supply chain details are in documents, cite them. Otherwise, describe regional/global housing supply patterns and note evidence limitations for {country_name}.",
        },
        {
            "title": "7. Rental Housing",
            "prompt": f"{base_instruction}Then write the Rental Housing section. ONLY provide {country_name} rental statistics, regulations, or programs if explicitly in documents. If documents discuss rental housing in Latin America generally, frame as regional context. Do NOT invent tenure percentages, rental programs, or legal frameworks without citations.",
        },
        {
            "title": "8. Housing Finance",
            "prompt": f"{base_instruction}Then write the Housing Finance section. Describe mortgage markets and housing finance based on document evidence. If documents cover Latin American housing finance patterns, state that explicitly. Do NOT claim {country_name} has specific mortgage products, interest rates, or financial institutions unless documented.",
        },
        {
            "title": "9. Government Housing Programs and Subsidies",
            "prompt": f"{base_instruction}Then write Government Housing Programs section. ONLY name {country_name} programs if explicitly mentioned in documents. If documents discuss subsidy approaches regionally/globally, describe those patterns and note they may apply to {country_name}. Do NOT invent program names, eligibility criteria, or coverage statistics.",
        },
        {
            "title": "10. Supply and Demand Analysis",
            "prompt": f"{base_instruction}Then write Supply and Demand Analysis. If documents provide {country_name} housing deficit data, use it. Otherwise, discuss regional housing deficit patterns and methodologies. Do NOT quantify {country_name}'s deficit without document support. Use qualifiers like 'regional evidence suggests...'.",
        },
        {
            "title": "11. Constraints and Opportunities",
            "prompt": f"{base_instruction}Then write Constraints and Opportunities. Synthesize findings from documents, distinguishing between {country_name}-specific evidence and regional/global patterns. Frame recommendations based on regional experience if {country_name} evidence is limited. Be explicit about evidence base for each claim.",
        },
    ]

SECTION_PROMPTS = [
    {
        "title": "1. Executive Summary",
        "prompt": "Write an Executive Summary for the housing market. Summarize market conditions, main constraints, and high-potential opportunities. Outline emerging trends and policy levers to ensure supply of affordable housing. Highlight priority interventions across the value chain.",
    },
    {
        "title": "2. Introduction of Purpose and Scope",
        "prompt": "Write the Introduction of Purpose and Scope. State that the report is designed to diagnose strengths and weaknesses of the housing market using the Housing Sector Value Chain as a framework. Clarify that this report serves as an entry point for further engagement. Describe the analytical framework and types of sources used.",
    },
    {
        "title": "3. National and Regional Context",
        "prompt": "Write the National and Regional Context section. Analyze the country's urban system, labor market, and macroeconomic trends. Present key demographic data. Summarize historical growth trends. Compare the country with its regional peers.",
    },
    {
        "title": "4. Housing Sector within the Economy",
        "prompt": "Write the 'Housing Sector within the Economy' section. Estimate the sector's contribution to GDP and employment (formal and informal). Assess the total economic impact of improvements in housing sector performance.",
    },
    {
        "title": "5. Institutional and Legal Framework",
        "prompt": "Write the Institutional and Legal Framework section. Summarize the legal framework governing the housing sector. Identify and describe the main institutions responsible for housing, including mandates, capacities, and constraints.",
    },
    {
        "title": "6. Housing Supply",
        "prompt": "Write the Housing Supply section. Characterize and assess the housing supply value chain: access to land, infrastructure, construction/materials. Discuss spatial patterns of housing development and the capacity of private developers.",
    },
    {
        "title": "7. Rental Housing",
        "prompt": "Write the Rental Housing section. Describe the structure and dynamics of the rental housing market. Summarize the legal and regulatory framework for rental housing.",
    },
    {
        "title": "8. Housing Finance",
        "prompt": "Write the Housing Finance section. Summarize the state of the mortgage finance market (products, institutions, depth). Analyze the structure, volume, and cost of housing finance. Review the construction finance sector.",
    },
    {
        "title": "9. Government Housing Programs and Subsidies",
        "prompt": "Write the Government Housing Programs and Subsidies section. Provide a brief chronology of government interventions. Summarize the design, coverage, eligibility, and performance of government housing programs.",
    },
    {
        "title": "10. Supply and Demand Analysis",
        "prompt": "Write the Supply and Demand Analysis section. Prepare a current snapshot of the housing market, comparing supply and demand. Quantify the housing deficit.",
    },
    {
        "title": "11. Constraints and Opportunities",
        "prompt": "Write the Constraints and Opportunities section. Synthesize the main constraints across the housing value chain. Recommend actions to unblock housing and strengthen the enabling environment.",
    },
]


class ReportService:
    def __init__(self, db_session: AsyncSession, runner: LangGraphRunner, settings: Settings):
        self._db_session = db_session
        self._runner = runner
        self._settings = settings
        self._doc_repo = DocumentRepository(db_session)
        self._convo_service = ConversationService(db_session)

    async def generate_housing_report(
        self,
        country_code: str,
        user_id: str,
        request_context: RequestContext,
        auth_context: AuthContext,
        skip_cache: bool = False,
    ) -> bytes:
        # Check S3 cache first unless skip_cache is requested
        if not skip_cache and self._settings.s3_housing_pdf_bucket:
            try:
                cached_pdf = get_cached_report(country_code, self._settings)
                if cached_pdf:
                    logger.info(f"Returning cached report for {country_code}")
                    return cached_pdf
            except Exception as e:
                logger.warning(f"Failed to fetch cached report (proceeding to generate): {e}")

        # 1. Get country name and generate prompts
        country_name = COUNTRY_NAME_BY_ALPHA3.get(country_code, country_code)
        country_name = _simplify_country_name(country_name)
        section_prompts = _get_section_prompts(country_name)
        
        # 2. Fetch all documents for the country
        documents = await self._doc_repo.list_documents_for_country(country_code)
        if not documents:
            logger.warning(f"No documents found for country {country_code}")
            # We might still want to generate a report saying "no data", or just proceed.
            # but the LLM will hallucinate if it has no context.
            # For now let's proceed, the agent might refuse or hallucinate.

        # 3. Generate Content for each section
        # Each section gets its own conversation to prevent response overloading
        sections_data = []
        document_index = {}  # Maps document_name -> citation number [1], [2], etc.

        for section_def in section_prompts:
            logger.info(f"Generating section: {section_def['title']}")

            # Create a separate conversation for this section
            conversation = await self._convo_service.ensure_conversation(
                owner_user_id=user_id,
                country_code=country_code,
                title=f"{section_def['title']} - {country_code}",
                namespace="report-generation",
                tags=["report", "housing", country_code],
            )

            # Attach documents to this section's conversation
            for doc in documents:
                try:
                    await self._doc_repo.attach_to_conversation(
                        conversation_id=conversation.id,
                        document_id=doc.id,
                        attach_source="report-generator",
                        visibility_override="hidden",  # Hidden so it doesn't clutter UI if user sees this convo
                    )
                except Exception as e:
                    logger.error(f"Failed to attach doc {doc.id}: {e}")

            # Generate unique thread_id per section
            thread_id = str(uuid4())

            chat_request = ChatRequestContext(
                conversation_id=str(conversation.id),
                thread_id=thread_id,
                session_id=None,
                allow_stateless=True,
                message=ChatMessagePayload(
                    type="user",
                    content=section_def["prompt"],
                    attachments=[],
                ),
                hints={
                    "country_code": country_code,
                    "retrieval_profile": "country_profile",
                },
                constraints={"country_code": country_code},  # type: ignore[arg-type]
                owner_user_id=user_id,
                workspace_id=None,
                tenant_id=auth_context.tenant_id,
            )

            try:
                result = await self._runner.run_chat(
                    request=chat_request,
                    auth=auth_context,
                    request_context=request_context,
                    sse_emitter=None,  # Blocking
                    prompt_overrides={},
                    hints={},
                    response_mode=ResponseMode.BLOCKING,
                    db_session=self._db_session,
                )

                markdown_content = result.done_payload.get("answer", "")
                citations = result.done_payload.get("citations", [])

                # Map chunk citations [c1], [c2] to document citations [1], [2]
                markdown_content, document_index = _map_chunk_citations_to_documents(
                    markdown_content,
                    citations,
                    document_index
                )

                # COMMENTED OUT: Old citation removal that stripped citations entirely
                # This removed [c1], [c2] markers but left no link to references
                # # Remove citation markers [c1][c2][cx] from the text
                # markdown_content = re.sub(r'\[c\d+\]', '', markdown_content)
                # # Clean up punctuation artifacts left by citation removal
                # markdown_content = re.sub(r',\s*\.', '.', markdown_content)  # ", ." → "."
                # markdown_content = re.sub(r',\s*,+', ',', markdown_content)  # ",," → ","
                # markdown_content = re.sub(r'\s+\.', '.', markdown_content)   # " ." → "."
                # markdown_content = re.sub(r'\s+,', ',', markdown_content)    # " ," → ","

                # Convert Markdown to HTML
                html_content = markdown.markdown(markdown_content)

                sections_data.append({"title": section_def["title"], "content": html_content})

            except Exception as e:
                logger.error(
                    f"Error generating section {section_def['title']}: {type(e).__name__}: {e}",
                    exc_info=True
                )
                sections_data.append(
                    {
                        "title": section_def["title"],
                        "content": "<p>The report is unable to develop an analysis for this section.</p>",
                    }
                )

        # 3. Build References section - numbered citations
        references = []
        # Sort by citation number [1], [2], [3], etc.
        for doc_name, citation_num in sorted(document_index.items(), key=lambda x: x[1]):
            references.append({
                "citation_number": citation_num,
                "document_name": doc_name,
            })

        # 4. Render PDF
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)))
        template = env.get_template("housing_report.html")

        rendered_html = template.render(
            country=country_code,
            date=datetime.now(UTC).strftime("%d %B %Y"),
            sections=sections_data,
            references=references,
        )

        pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()

        # 5. Upload to S3 cache (non-blocking)
        if self._settings.s3_housing_pdf_bucket:
            try:
                upload_cached_report(country_code, pdf_bytes, self._settings)
                logger.info(f"Cached report for {country_code}")
            except Exception as e:
                logger.warning(f"Failed to upload report to cache (non-fatal): {e}")

        return pdf_bytes
