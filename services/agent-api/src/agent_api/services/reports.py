import asyncio
import logging
import re
import time
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
from agent_api.http.errors import GatewayError
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
    return country_name.split(",")[0].strip()


def _map_chunk_citations_to_documents(
    markdown_content: str, citations: list[dict], document_index: dict[str, int]
) -> tuple[str, dict[str, int]]:
    """Map chunk-based citations [c1], [c2] to document-based citations [1], [2].

    Deduplicates consecutive citations so [1][1][1] becomes [1] and [1][2][1] becomes [1][2].
    Preserves citation placement relative to punctuation: "text. [1][2]" stays as-is.
    """
    chunk_to_doc_citation = {}

    for idx, citation in enumerate(citations, start=1):
        doc_name = citation.get("canonical_name") or citation.get("doc_id", "Unknown")
        chunk_citation = f"c{idx}"

        if doc_name not in document_index:
            document_index[doc_name] = len(document_index) + 1

        doc_citation_num = document_index[doc_name]
        chunk_to_doc_citation[chunk_citation] = doc_citation_num

    for chunk_cit, doc_num in chunk_to_doc_citation.items():
        markdown_content = markdown_content.replace(f"[{chunk_cit}]", f"[{doc_num}]")

    def deduplicate_citation_group(match):
        group = match.group(0)
        citation_nums = re.findall(r"\[(\d+)\]", group)

        seen = set()
        unique_citations = []
        for num in citation_nums:
            if num not in seen:
                unique_citations.append(num)
                seen.add(num)

        trailing = ""
        after_citations = group[group.rfind("]") + 1 :]

        punct_match = re.match(r"^[,.\-\s]*([.,;!?])(\s*)", after_citations)
        if punct_match and (
            punct_match.group(2)
            or not re.match(r"^\d", after_citations[len(punct_match.group()) :])
        ):
            trailing = punct_match.group(1) + punct_match.group(2)

        return "".join(f"[{num}]" for num in unique_citations) + trailing

    markdown_content = re.sub(
        r"\[\d+\](?:[,.\-\s]*\[\d+\])*[,.\-\s]*(?=[A-Z]|[a-z]|$)",
        deduplicate_citation_group,
        markdown_content,
    )

    markdown_content = re.sub(r"([^\s\]])(\[\d+\])", r"\1 \2", markdown_content)
    markdown_content = re.sub(r"(\])([^\s\]\[\.,;!?\d])", r"\1 \2", markdown_content)

    markdown_content = re.sub(
        r"([.,;!?])\s+(\[\d+\](?:\s*\[\d+\])*)",
        lambda m: f" {m.group(2)}{m.group(1)} "
        if m.end() < len(m.string) and m.string[m.end()].isalpha()
        else f" {m.group(2)}{m.group(1)}",
        markdown_content,
    )

    markdown_content = re.sub(r"[^\S\n]{2,}", " ", markdown_content)

    return markdown_content, document_index


_FAILURE_PATTERNS: list[str] = [
    "i'm sorry",
    "i am sorry",
    "couldn't produce a response",
    "could not produce a response",
    "unable to develop an analysis",
    "unable to produce cited answer",
    "no information available",
    "no data available",
    "i don't have enough information",
    "i do not have enough information",
]

_MIN_SECTION_CHARS = 80


def _is_section_content_valid(markdown_content: str, citations: list[dict]) -> tuple[bool, str]:
    """Return (valid, reason) for a generated section's raw markdown content."""
    stripped = markdown_content.strip()
    if not stripped:
        return False, "empty response"
    if len(stripped) < _MIN_SECTION_CHARS:
        return False, f"response too short ({len(stripped)} chars, min {_MIN_SECTION_CHARS})"
    if not citations:
        return False, "missing citations"
    if "[c" not in stripped.lower():
        return False, "response missing inline citation markers"
    lower = stripped.lower()
    for pattern in _FAILURE_PATTERNS:
        if pattern in lower:
            return False, f"failure pattern detected: '{pattern}'"
    return True, "ok"


def _force_two_paragraphs(text: str) -> str:
    if "\n\n" in text.strip():
        return text

    sentence_end = re.compile(
        r"""
        (?:                     # citation cluster (optional)
            (?:\s*\[\w+\])+     # one or more [c1], [2], etc.
        )?
        \.\s+                   # period followed by whitespace
        """,
        re.VERBOSE,
    )

    spans = list(sentence_end.finditer(text))
    if len(spans) < 2:
        return text

    midpoint = len(text) // 2
    best = min(spans, key=lambda m: abs(m.end() - midpoint))
    split_pos = best.end()

    return text[:split_pos].rstrip() + "\n\n" + text[split_pos:].lstrip()


def _get_section_prompts(country_name: str) -> list[dict[str, str]]:
    """Generate clean, focused section prompts with country name injected.

    The system prompt (_COUNTRY_PROFILE_SYSTEM_PROMPT) already enforces
    retrieval-first behavior, 2-paragraph format, citation requirements,
    and no bullet points. These prompts only need to specify the topic
    and a fallback strategy for thin country-specific evidence.
    """
    fallback = (
        f"If {country_name}-specific evidence is limited, you may draw on regional and global "
        f"documents, but you MUST clearly state when a finding comes from regional or global "
        f"sources rather than {country_name}-specific evidence. "
        f"Use qualifiers like 'Across the region...' or 'Global evidence suggests...' "
        f"for non-country-specific sources."
    )
    return [
        {
            "title": "1. Executive Summary",
            "prompt": (
                f"Summarize {country_name}'s housing market conditions, main constraints, "
                f"and high-potential opportunities. Highlight emerging trends and policy levers "
                f"for affordable housing supply. {fallback}"
            ),
        },
        {
            "title": "2. Introduction of Purpose and Scope",
            "prompt": (
                f"Introduce the purpose and scope of this housing sector diagnostic for "
                f"{country_name}. Describe the analytical framework used and the types of "
                f"evidence sources consulted. {fallback}"
            ),
        },
        {
            "title": "3. National and Regional Context",
            "prompt": (
                f"Describe {country_name}'s national and regional context relevant to housing: "
                f"urban system, demographic trends, labor market conditions, and macroeconomic "
                f"factors. Compare with regional peers where applicable. {fallback}"
            ),
        },
        {
            "title": "4. Housing Sector within the Economy",
            "prompt": (
                f"Analyze the role of {country_name}'s housing sector within its economy, "
                f"including contributions to GDP, employment in formal and informal construction, "
                f"and the broader economic impact of housing sector performance. {fallback}"
            ),
        },
        {
            "title": "5. Institutional and Legal Framework",
            "prompt": (
                f"Describe the institutional and legal framework governing {country_name}'s "
                f"housing sector. Identify the main institutions responsible for housing policy, "
                f"their mandates, capacities, and key constraints. {fallback}"
            ),
        },
        {
            "title": "6. Housing Supply",
            "prompt": (
                f"Characterize {country_name}'s housing supply value chain: access to land, "
                f"infrastructure provision, construction materials, and the capacity of private "
                f"developers. Discuss spatial patterns of housing development. {fallback}"
            ),
        },
        {
            "title": "7. Rental Housing",
            "prompt": (
                f"Describe the structure and dynamics of {country_name}'s rental housing market, "
                f"including tenure patterns, the legal and regulatory framework for rental "
                f"housing, and key challenges facing renters. {fallback}"
            ),
        },
        {
            "title": "8. Housing Finance",
            "prompt": (
                f"Describe the state of {country_name}'s housing finance sector, including "
                f"mortgage market depth, key financial institutions, products available, "
                f"construction finance, and access to housing credit. {fallback}"
            ),
        },
        {
            "title": "9. Government Housing Programs and Subsidies",
            "prompt": (
                f"Describe {country_name}'s government housing programs and subsidies, including "
                f"their design, coverage, eligibility criteria, and performance. Note the "
                f"chronology of key government interventions in housing. {fallback}"
            ),
        },
        {
            "title": "10. Supply and Demand Analysis",
            "prompt": (
                f"Analyze {country_name}'s housing supply and demand balance. Describe the "
                f"current housing deficit, its composition across income segments, and the "
                f"methodologies used to quantify it. {fallback}"
            ),
        },
        {
            "title": "11. Constraints and Opportunities",
            "prompt": (
                f"Synthesize the main constraints across {country_name}'s housing value chain "
                f"and identify priority opportunities. Recommend actions to unblock housing "
                f"supply and strengthen the enabling environment. {fallback}"
            ),
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
        upload_cache: bool = True,
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
        if country_code == "TUR":
            country_name = "Türkiye"
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

        _MAX_SECTION_ATTEMPTS = 3
        _INTER_SECTION_DELAY_S = 2.0
        _RETRY_DELAY_S = 5.0

        for section_idx, section_def in enumerate(section_prompts):
            section_title = section_def["title"]

            if section_idx > 0:
                await asyncio.sleep(_INTER_SECTION_DELAY_S)

            logger.info(
                "report.section.start",
                extra={"country": country_code, "section": section_title},
            )

            section_html: str | None = None
            last_failure_reason: str = "unknown"

            for attempt in range(1, _MAX_SECTION_ATTEMPTS + 1):
                if attempt > 1:
                    await asyncio.sleep(_RETRY_DELAY_S)
                attempt_start = time.monotonic()
                logger.info(
                    "report.section.attempt",
                    extra={
                        "country": country_code,
                        "section": section_title,
                        "attempt": attempt,
                        "max_attempts": _MAX_SECTION_ATTEMPTS,
                    },
                )

                try:
                    conversation = await self._convo_service.ensure_conversation(
                        owner_user_id=user_id,
                        country_code=country_code,
                        title=f"{section_title} - {country_code} (attempt {attempt})",
                        namespace="report-generation",
                        tags=["report", "housing", country_code],
                    )

                    for doc in documents:
                        try:
                            await self._doc_repo.attach_to_conversation(
                                conversation_id=conversation.id,
                                document_id=doc.id,
                                attach_source="report-generator",
                                visibility_override="hidden",
                            )
                        except Exception as doc_err:
                            logger.error(
                                "report.section.doc_attach_failed",
                                extra={
                                    "country": country_code,
                                    "section": section_title,
                                    "doc_id": str(doc.id),
                                    "error": str(doc_err),
                                },
                            )

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

                    result = await self._runner.run_chat(
                        request=chat_request,
                        auth=auth_context,
                        request_context=request_context,
                        sse_emitter=None,
                        prompt_overrides={},
                        hints={},
                        response_mode=ResponseMode.BLOCKING,
                        db_session=self._db_session,
                    )

                    raw_markdown = result.done_payload.get("answer", "")
                    citations = result.done_payload.get("citations", [])

                    valid, reason = _is_section_content_valid(raw_markdown, citations)
                    elapsed = round(time.monotonic() - attempt_start, 2)

                    if not valid:
                        last_failure_reason = reason
                        logger.warning(
                            "report.section.invalid_content",
                            extra={
                                "country": country_code,
                                "section": section_title,
                                "attempt": attempt,
                                "reason": reason,
                                "content_preview": raw_markdown[:120],
                                "elapsed_s": elapsed,
                            },
                        )
                        continue

                    mapped_markdown, document_index = _map_chunk_citations_to_documents(
                        raw_markdown, citations, document_index
                    )
                    mapped_markdown = _force_two_paragraphs(mapped_markdown)
                    html_content = markdown.markdown(mapped_markdown)
                    html_content = re.sub(
                        r"\[(\d+)\]",
                        r'<sup><a href="#ref-\1" class="citation-link">[\1]</a></sup>',
                        html_content,
                    )

                    section_html = html_content
                    logger.info(
                        "report.section.success",
                        extra={
                            "country": country_code,
                            "section": section_title,
                            "attempt": attempt,
                            "elapsed_s": elapsed,
                        },
                    )
                    break

                except Exception as exc:
                    elapsed = round(time.monotonic() - attempt_start, 2)
                    last_failure_reason = f"{type(exc).__name__}: {exc}"
                    logger.warning(
                        "report.section.exception",
                        extra={
                            "country": country_code,
                            "section": section_title,
                            "attempt": attempt,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                            "elapsed_s": elapsed,
                        },
                        exc_info=True,
                    )

            if section_html is not None:
                sections_data.append({"title": section_title, "content": section_html})
            else:
                logger.error(
                    "report.section.all_attempts_failed",
                    extra={
                        "country": country_code,
                        "section": section_title,
                        "attempts": _MAX_SECTION_ATTEMPTS,
                        "last_failure_reason": last_failure_reason,
                    },
                )
                raise GatewayError(
                    code="REPORT_SECTION_INCOMPLETE",
                    message=(
                        f"Report generation failed for {country_code}: "
                        f"section '{section_title}' did not complete after "
                        f"{_MAX_SECTION_ATTEMPTS} attempts."
                    ),
                    status_code=502,
                    details={
                        "country_code": country_code,
                        "section": section_title,
                        "attempts": _MAX_SECTION_ATTEMPTS,
                        "last_failure_reason": last_failure_reason,
                    },
                )

        # 3. Build References section - numbered citations
        references = []
        # Sort by citation number [1], [2], [3], etc.
        for doc_name, citation_num in sorted(document_index.items(), key=lambda x: x[1]):
            references.append(
                {
                    "citation_number": citation_num,
                    "document_name": doc_name,
                }
            )

        # 4. Render PDF
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)))
        template = env.get_template("housing_report.html")

        rendered_html = template.render(
            country=country_name,
            date=datetime.now(UTC).strftime("%d %B %Y"),
            sections=sections_data,
            references=references,
        )

        pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()

        # 5. Upload to S3 cache (non-blocking)
        if upload_cache and self._settings.s3_housing_pdf_bucket:
            try:
                upload_cached_report(country_code, pdf_bytes, self._settings)
                logger.info(f"Cached report for {country_code}")
            except Exception as e:
                logger.warning(f"Failed to upload report to cache (non-fatal): {e}")

        return pdf_bytes
