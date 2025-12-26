
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List, Dict
from uuid import uuid4

import jinja2
import markdown
import weasyprint
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.agent.runner import LangGraphRunner
from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.schemas import ResponseMode, ChatMessagePayload
from agent_api.models.chat import ChatRequestContext
from agent_api.report_cache import get_cached_report, upload_cached_report
from agent_api.services.conversations import ConversationService
from agent_api.settings import Settings
from shared_data_layer.repositories.documents import DocumentRepository

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

SECTION_PROMPTS = [
    {
        "title": "1. Executive Summary",
        "prompt": "Write an Executive Summary for the housing market. Summarize market conditions, main constraints, and high-potential opportunities. Outline emerging trends and policy levers to ensure supply of affordable housing. Highlight priority interventions across the value chain."
    },
    {
        "title": "2. Introduction of Purpose and Scope",
        "prompt": "Write the Introduction of Purpose and Scope. State that the report is designed to diagnose strengths and weaknesses of the housing market using the Housing Sector Value Chain as a framework. Clarify that this report serves as an entry point for further engagement. Describe the analytical framework and types of sources used."
    },
    {
        "title": "3. National and Regional Context",
        "prompt": "Write the National and Regional Context section. Analyze the country's urban system, labor market, and macroeconomic trends. Present key demographic data. Summarize historical growth trends. Compare the country with its regional peers."
    },
    {
        "title": "4. Housing Sector within the Economy",
        "prompt": "Write the 'Housing Sector within the Economy' section. Estimate the sector's contribution to GDP and employment (formal and informal). Assess the total economic impact of improvements in housing sector performance."
    },
    {
        "title": "5. Institutional and Legal Framework",
        "prompt": "Write the Institutional and Legal Framework section. Summarize the legal framework governing the housing sector. Identify and describe the main institutions responsible for housing, including mandates, capacities, and constraints."
    },
    {
        "title": "6. Housing Supply",
        "prompt": "Write the Housing Supply section. Characterize and assess the housing supply value chain: access to land, infrastructure, construction/materials. Discuss spatial patterns of housing development and the capacity of private developers."
    },
    {
        "title": "7. Rental Housing",
        "prompt": "Write the Rental Housing section. Describe the structure and dynamics of the rental housing market. Summarize the legal and regulatory framework for rental housing."
    },
    {
        "title": "8. Housing Finance",
        "prompt": "Write the Housing Finance section. Summarize the state of the mortgage finance market (products, institutions, depth). Analyze the structure, volume, and cost of housing finance. Review the construction finance sector."
    },
     {
        "title": "9. Government Housing Programs and Subsidies",
        "prompt": "Write the Government Housing Programs and Subsidies section. Provide a brief chronology of government interventions. Summarize the design, coverage, eligibility, and performance of government housing programs."
    },
     {
        "title": "10. Supply and Demand Analysis",
        "prompt": "Write the Supply and Demand Analysis section. Prepare a current snapshot of the housing market, comparing supply and demand. Quantify the housing deficit."
    },
     {
        "title": "11. Constraints and Opportunities",
        "prompt": "Write the Constraints and Opportunities section. Synthesize the main constraints across the housing value chain. Recommend actions to unblock housing and strengthen the enabling environment."
    }
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
    ) -> bytes:
        # 0. Check for cached report in S3
        if self._settings.s3_housing_pdf_bucket:
            cached_report = get_cached_report(country_code, self._settings)
            if cached_report is not None:
                logger.info(f"Returning cached report for country {country_code}")
                return cached_report

        # 1. Fetch all documents for the country
        documents = await self._doc_repo.list_documents_for_country(country_code)
        if not documents:
            logger.warning(f"No documents found for country {country_code}")
             # We might still want to generate a report saying "no data", or just proceed.
             # but the LLM will hallucinate if it has no context.
             # For now let's proceed, the agent might refuse or hallucinate.
        
        # 2. Create a temporary conversation
        conversation = await self._convo_service.ensure_conversation(
            owner_user_id=user_id,
            country_code=country_code,
            title=f"Housing Report Generation - {country_code}",
            namespace="report-generation",
            tags=["report", "housing", country_code],
        )

        # 3. Attach documents to the conversation
        for doc in documents:
            try:
                await self._doc_repo.attach_to_conversation(
                    conversation_id=conversation.id,
                    document_id=doc.id,
                    attach_source="report-generator",
                    visibility_override="hidden", # Hidden so it doesn't clutter UI if user sees this convo
                )
            except Exception as e:
                logger.error(f"Failed to attach doc {doc.id}: {e}")

        # 4. Generate Content for each section
        sections_data = []
        all_citations = {}  # Map document_name -> document info (for unique docs)
        
        # Use a fresh thread ID for the whole report so context is shared
        thread_id = str(uuid4())

        for section_def in SECTION_PROMPTS:
            logger.info(f"Generating section: {section_def['title']}")
            
            chat_request = ChatRequestContext(
                conversation_id=str(conversation.id),
                thread_id=thread_id,
                session_id=None,
                allow_stateless=False,
                message=ChatMessagePayload(
                    type="user",
                    content=section_def["prompt"],
                    attachments=[],
                ),
                hints={"country_code": country_code},
                constraints={"country_code": country_code},
                owner_user_id=user_id,
                workspace_id=None,
                tenant_id=auth_context.tenant_id,
            )

            try:
                result = await self._runner.run_chat(
                    request=chat_request,
                    auth=auth_context,
                    request_context=request_context,
                    sse_emitter=None, # Blocking
                    prompt_overrides={},
                    hints={},
                    response_mode=ResponseMode.BLOCKING,
                    db_session=self._db_session,
                )
                
                markdown_content = result.done_payload.get("answer", "")
                citations = result.done_payload.get("citations", [])
                
                # Collect citations grouped by document
                # Format: {"doc_id", "chunk_id", "canonical_name", "page_number", "position", "text", "score"}
                # Citations are numbered [c1]-[c8] per retrieval
                for idx, citation in enumerate(citations, start=1):
                    doc_name = citation.get("canonical_name") or citation.get("doc_id", "Unknown")
                    
                    # Group citation numbers by document name
                    if doc_name not in all_citations:
                        all_citations[doc_name] = {
                            "document_name": doc_name,
                            "citation_numbers": [],
                        }
                    # Add citation number if not already present
                    if idx not in all_citations[doc_name]["citation_numbers"]:
                        all_citations[doc_name]["citation_numbers"].append(idx)
                
                # Convert Markdown to HTML
                html_content = markdown.markdown(markdown_content)
                
                sections_data.append({
                    "title": section_def["title"],
                    "content": html_content
                })

            except Exception as e:
                logger.error(f"Error generating section {section_def['title']}: {e}")
                sections_data.append({
                    "title": section_def["title"],
                    "content": f"<p>Error generating content: {str(e)}</p>"
                })

        # 5. Build References section - group citations by document
        references = []
        for doc_name, citation_info in all_citations.items():
            # Format citation numbers like [c1][c2][c4]
            citation_nums = sorted(citation_info["citation_numbers"])
            citations_str = "".join(f"[c{n}]" for n in citation_nums)
            references.append({
                "citations": citations_str,
                "document_name": citation_info["document_name"],
            })
        
        # Sort by document name for consistency
        references.sort(key=lambda x: x["document_name"])
        
        # 6. Render PDF
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR))
        )
        template = env.get_template("housing_report.html")
        
        rendered_html = template.render(
            country=country_code,
            date=datetime.now().strftime("%d %B %Y"),
            sections=sections_data,
            references=references
        )

        pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()
        
        # 7. Upload to S3 cache (non-blocking)
        if self._settings.s3_housing_pdf_bucket:
            try:
                upload_cached_report(country_code, pdf_bytes, self._settings)
            except Exception as e:
                logger.warning(f"Failed to upload report to cache (non-fatal): {e}")
        
        return pdf_bytes
