"""Cache preprocessing service for pillar questions."""

from __future__ import annotations

import logging
from typing import TypedDict
from uuid import uuid4

from shared_data_layer.db.models import Document
from shared_data_layer.db.session import DatabaseSessionManager
from shared_data_layer.repositories.documents import DocumentRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.agent.runner import ChatRunnerProtocol
from agent_api.auth.validator import AuthContext
from agent_api.http.context import RequestContext
from agent_api.http.schemas import ChatConstraints, ChatMessagePayload, ResponseMode
from agent_api.models.chat import ChatRequestContext
from agent_api.services.cache import ChatCacheService
from agent_api.services.conversations import ConversationService

logger = logging.getLogger(__name__)

# Allowed countries for preprocessing (from frontend country list)
ALLOWED_COUNTRIES = {
    "AFG",
    "ALB",
    "DZA",
    "ASM",
    "AND",
    "AGO",
    "AIA",
    "ATA",
    "ATG",
    "ARG",
    "ARM",
    "ABW",
    "AUS",
    "AUT",
    "AZE",
    "BHS",
    "BHR",
    "BGD",
    "BRB",
    "BLR",
    "BEL",
    "BLZ",
    "BEN",
    "BMU",
    "BTN",
    "BOL",
    "BIH",
    "BWA",
    "BVT",
    "BRA",
    "IOT",
    "BRN",
    "BGR",
    "BFA",
    "BDI",
    "KHM",
    "CMR",
    "CAN",
    "CPV",
    "CYM",
    "CAF",
    "TCD",
    "CHL",
    "CHN",
    "CXR",
    "CCK",
    "COL",
    "COM",
    "COG",
    "COD",
    "COK",
    "CRI",
    "CIV",
    "HRV",
    "CUB",
    "CYP",
    "CZE",
    "DNK",
    "DJI",
    "DMA",
    "DOM",
    "ECU",
    "EGY",
    "SLV",
    "GNQ",
    "ERI",
    "EST",
    "ETH",
    "FLK",
    "FRO",
    "FJI",
    "FIN",
    "FRA",
    "GUF",
    "PYF",
    "ATF",
    "GAB",
    "GMB",
    "GEO",
    "DEU",
    "GHA",
    "GIB",
    "GRC",
    "GRL",
    "GRD",
    "GLP",
    "GUM",
    "GTM",
    "GIN",
    "GNB",
    "GUY",
    "HTI",
    "HMD",
    "VAT",
    "HND",
    "HKG",
    "HUN",
    "ISL",
    "IND",
    "IDN",
    "IRN",
    "IRQ",
    "IRL",
    "ISR",
    "ITA",
    "JAM",
    "JPN",
    "JOR",
    "KAZ",
    "KEN",
    "KIR",
    "PRK",
    "KOR",
    "KWT",
    "KGZ",
    "LAO",
    "LVA",
    "LBN",
    "LSO",
    "LBR",
    "LBY",
    "LIE",
    "LTU",
    "LUX",
    "MAC",
    "MKD",
    "MDG",
    "MWI",
    "MYS",
    "MDV",
    "MLI",
    "MLT",
    "MHL",
    "MTQ",
    "MRT",
    "MUS",
    "MYT",
    "MEX",
    "FSM",
    "MDA",
    "MCO",
    "MNG",
    "MNE",
    "MSR",
    "MAR",
    "MOZ",
    "MMR",
    "NAM",
    "NRU",
    "NPL",
    "NLD",
    "NCL",
    "NZL",
    "NIC",
    "NER",
    "NGA",
    "NIU",
    "NFK",
    "MNP",
    "NOR",
    "OMN",
    "PAK",
    "PLW",
    "PSE",
    "PAN",
    "PNG",
    "PRY",
    "PER",
    "PHL",
    "PCN",
    "POL",
    "PRT",
    "PRI",
    "QAT",
    "REU",
    "ROU",
    "RUS",
    "RWA",
    "SHN",
    "KNA",
    "LCA",
    "SPM",
    "VCT",
    "WSM",
    "SMR",
    "STP",
    "SAU",
    "SEN",
    "SRB",
    "SYC",
    "SLE",
    "SGP",
    "SVK",
    "SVN",
    "SLB",
    "SOM",
    "ZAF",
    "SGS",
    "ESP",
    "LKA",
    "SDN",
    "SUR",
    "SJM",
    "SWZ",
    "SWE",
    "CHE",
    "SYR",
    "TWN",
    "TJK",
    "TZA",
    "THA",
    "TLS",
    "TGO",
    "TKL",
    "TON",
    "TTO",
    "TUN",
    "TUR",
    "TKM",
    "TCA",
    "TUV",
    "UGA",
    "UKR",
    "ARE",
    "GBR",
    "USA",
    "UMI",
    "URY",
    "UZB",
    "VUT",
    "VEN",
    "VNM",
    "VGB",
    "VIR",
    "WLF",
    "ESH",
    "YEM",
    "ZMB",
    "ZWE",
}

# Pillar Questions - 50 total across 5 pillars.
# Must stay in sync with frontend PILLAR_CONTENT (housing-sector-context, policies-institutions,
# government-programs, housing-supply-chain, developer-end-user-finance). Cache is keyed by
# country_code + question text hash; question text must match exactly for cache hits.
PILLAR_QUESTIONS = {
    "Sector Context": [  # pillarId: housing-sector-context
        "What is the housing sector's contribution to GDP and employment, including both direct and indirect economic effects?",
        "What is the scale and geographic distribution of housing need (quantitative deficit, qualitative deficit, overcrowding, backyard shacks, informal settlements)?",
        "What are typical household incomes and affordability levels, and how do these compare to the cost of formal housing?",
        "What market segments are underserved (low-income, rental, youth, informal workers, households in peri-urban areas)?",
        "What is the size and nature of the housing deficit, differentiated by regions, cities, and income groups?",
        "What is the structure and dynamics of the rental housing market, including typical terms, pricing, and registration practices?",
        "How is population growth, migration, and urbanization shaping demand for housing?",
        "What are the housing conditions and vulnerabilities of informal settlements?",
        "What are the spatial patterns of housing development (location, density) and what are their implications for urban growth?",
        "What would be the potential economic impact of improvements in housing sector performance, such as increases in private investment, job creation, and household wealth?",
    ],
    "Policies and Institutions": [  # pillarId: policies-institutions
        "Who are the main institutions responsible for housing, and what are their mandates, capacities, and constraints?",
        "What is the legal framework governing the housing sector and what potential gaps or weaknesses exist?",
        "What is the legal and regulatory framework for rental housing, including taxation and eviction procedures?",
        "What role do sub-national governments play in housing policy, program design, and delivery, and how effective are they?",
        "What are the financial and operational constraints of local municipalities in delivering serviced land?",
        "How sustainable are municipal financing models, especially for land servicing, cost recovery, and tariffs?",
        "What is the capacity of local governments to partner with private developers for infrastructure provision?",
        "What are the key policy and institutional constraints affecting the housing sector?",
    ],
    "Government Programs": [  # pillarId: government-programs
        "What is the chronology of government interventions in the housing sector, and what have been the successes and failures?",
        "What role do social and public housing programs play, and how financially sustainable are they?",
        "What are the design, coverage, eligibility criteria, and performance of government housing programs in the last 10 years?",
        "What are the main constraints to upgrading informal settlements, including affordability, tenure insecurity, and service gaps?",
        "What are the key strengths and weaknesses of government programs to support affordable housing?",
    ],
    "Supply Chain": [  # pillarId: housing-supply-chain
        "How accessible, available, and affordable is urban land for housing development?",
        "How efficient and transparent are land administration systems, including titling, deeds registration, and subdivision?",
        "How effective are the planning, zoning, and building regulatory systems, and where do bottlenecks delay delivery?",
        "How restrictive are zoning and building codes, and where could regulatory flexibility enable lower-cost delivery?",
        "How do spatial patterns (low density, urban sprawl, location of jobs) affect housing affordability and access to services?",
        "What is the capacity of local governments to service land with infrastructure (water, sanitation, electricity, roads)?",
        "What are the primary drivers of high construction costs (materials, logistics, regulation, labor, procurement)?",
        "What is the current and potential scale of alternative, lower-cost construction technologies?",
        "What is the role and capacity of public developers vs. private developers in supplying affordable units?",
        "What are the barriers preventing small and medium developers from scaling up?",
        "What are the constraints to formal rental development (regulatory, financial, land availability)?",
        "What are the key constraints affecting housing supply?",
    ],
    "Finance": [  # pillarId: developer-end-user-finance
        "What is the structure, volume, and share of housing finance in the financial sector and economy, including metrics such as total outstanding mortgage debt-to-GDP, volume of mortgages per year, and share of mortgage borrowers in adult population?",
        "What are the constraints on lenders (risk appetite, capital adequacy, foreclosure processes, collateral valuation)?",
        "What are the key conventional housing finance products and terms available?",
        "What legal and regulatory factors influence housing finance and mortgage market growth?",
        "What are the key barriers to mortgage access, especially for low and middle income households?",
        "What are current mortgage lending patterns, approval rates, NPLs, and interest rates?",
        "How inclusive are mortgage products for lower-income, informal, or self-employed households?",
        "What non-mortgage housing finance products exist (microfinance, cooperative finance, employer-assisted housing)?",
        "What characterizes the microfinance market as a whole, including its volume, actors and capacity to provide loans for home improvements and incremental construction?",
        "What is the role and capacity of housing microfinance (HMF) for home improvement and incremental construction? What are the constraints and opportunities for expanding HMF lending?",
        "How accessible is developer finance (both equity and debt) for land acquisition, pre-development, and vertical construction?",
        "What pre-sale, equity contribution, or collateral requirements do banks impose, and how do these affect developers' ability to launch projects?",
        "Are construction loans available at scale for affordable housing projects, and how do interest rates and loan tenures compare to regional benchmarks?",
        "What regulatory, risk management, or capital adequacy constraints limit banks from financing developers?",
        "What are the key constraints affecting access to finance for housing?",
    ],
}


async def get_countries_with_documents() -> list[str]:
    """
    Get list of country codes that have active documents.

    Returns:
        List of ISO-3 country codes
    """
    async with DatabaseSessionManager.session() as session:
        stmt = select(Document.country_code).where(Document.status == "active").distinct()
        result = await session.execute(stmt)
        countries = [row[0] for row in result.fetchall() if row[0]]
        return sorted(countries)


class PreprocessingStats(TypedDict):
    country_code: str
    total_questions: int
    cache_hits: int
    cache_generated: int
    errors: int


async def preprocess_cache_for_country(
    country_code: str,
    runner: ChatRunnerProtocol,
    db_session: AsyncSession,
    force_regenerate: bool = False,
) -> PreprocessingStats:
    """
    Preprocess cache for all pillar questions for a given country.

    Args:
        country_code: ISO-3 country code
        runner: Chat runner instance
        db_session: Database session
        force_regenerate: If True, always generate responses and do not skip cache hits.

    Returns:
        Dictionary with statistics about the preprocessing
    """
    cache_service = ChatCacheService(db_session)
    convo_service = ConversationService(db_session)
    doc_repo = DocumentRepository(db_session)

    stats: PreprocessingStats = {
        "country_code": country_code,
        "total_questions": 0,
        "cache_hits": 0,
        "cache_generated": 0,
        "errors": 0,
    }

    logger.info(f"[{country_code}] Starting cache preprocessing")
    print(f"[{country_code}] Starting cache preprocessing...")

    # Create a temporary conversation for this country and attach documents
    conversation = await convo_service.ensure_conversation(
        owner_user_id="00000000-0000-0000-0000-000000000000",  # System user
        country_code=country_code,
        title=f"Preprocessing - {country_code}",
        namespace="preprocessing",
        tags=["preprocessing", country_code],
    )

    # Get and attach all documents for this country
    documents = await doc_repo.list_documents_for_country(country_code)
    if not documents:
        logger.warning(
            f"[{country_code}] No documents found (including regional/global), skipping preprocessing"
        )
        print(f"[{country_code}] WARNING: No documents found, skipping")
        return stats

    print(f"[{country_code}] Found {len(documents)} documents (country/regional/global)")
    logger.info(f"[{country_code}] Found {len(documents)} documents to attach")

    for doc in documents:
        try:
            await doc_repo.attach_to_conversation(
                conversation_id=conversation.id,
                document_id=doc.id,
                attach_source="preprocessing",
                visibility_override="hidden",
            )
        except Exception as e:
            logger.warning(f"[{country_code}] Failed to attach doc {doc.id}: {e}")

    total_questions = sum(len(questions) for questions in PILLAR_QUESTIONS.values())
    question_num = 0

    for pillar_name, questions in PILLAR_QUESTIONS.items():
        print(f"[{country_code}] Processing pillar: {pillar_name} ({len(questions)} questions)")
        logger.info(
            f"[{country_code}] Processing pillar: {pillar_name} ({len(questions)} questions)"
        )

        for question in questions:
            question_num += 1
            stats["total_questions"] += 1

            try:
                if not force_regenerate:
                    cached = await cache_service.get_cached_response(country_code, question)
                    if cached is not None:
                        stats["cache_hits"] += 1
                        if question_num % 10 == 0:
                            print(
                                f"[{country_code}] Cache hit {question_num}/{total_questions}: {question[:50]}..."
                            )
                        logger.debug(
                            f"[{country_code}] Cache hit {question_num}/{total_questions}: {question[:50]}..."
                        )
                        continue

                print(
                    f"[{country_code}] Generating {question_num}/{total_questions}: {question[:60]}..."
                )
                logger.info(
                    f"[{country_code}] Generating {question_num}/{total_questions}: {question[:60]}..."
                )

                auth = AuthContext(
                    user_id=None,
                    tenant_id=None,
                    roles=None,
                    scopes=None,
                    metadata=None,
                )

                max_attempts = 3
                last_error: Exception | None = None
                completed = False
                for attempt in range(1, max_attempts + 1):
                    request_context = RequestContext(
                        request_id=f"preprocess-{country_code}-{stats['total_questions']}-a{attempt}",
                        traceparent=None,
                        idempotency_key=None,
                        headers={},
                    )
                    chat_request = ChatRequestContext(
                        conversation_id=str(conversation.id),
                        thread_id=str(uuid4()),
                        session_id=None,
                        allow_stateless=False,
                        message=ChatMessagePayload(content=question),
                        hints={"retrieval_profile": "country_profile"},
                        constraints=ChatConstraints(country_code=country_code),
                        owner_user_id="00000000-0000-0000-0000-000000000000",
                        workspace_id=None,
                        tenant_id=None,
                    )
                    try:
                        if attempt > 1:
                            print(
                                f"[{country_code}] Retry {attempt}/{max_attempts} for "
                                f"{question_num}/{total_questions}: {question[:60]}..."
                            )
                            logger.warning(
                                f"[{country_code}] Retry {attempt}/{max_attempts} for "
                                f"{question_num}/{total_questions}: {question[:60]}..."
                            )
                        result = await runner.run_chat(
                            request=chat_request,
                            auth=auth,
                            request_context=request_context,
                            sse_emitter=None,
                            prompt_overrides={},
                            hints={"retrieval_profile": "country_profile"},
                            response_mode=ResponseMode.BLOCKING,
                            db_session=db_session,
                        )
                        if result and result.done_payload:
                            response_data = {
                                "thread_id": chat_request.thread_id,
                                "request_id": request_context.request_id,
                                "done": result.done_payload,
                                "messages": result.messages or [],
                            }
                            await cache_service.store_response(country_code, question, response_data)
                            stats["cache_generated"] += 1
                            print(
                                f"[{country_code}] ✓ Cached {question_num}/{total_questions}: {question[:60]}..."
                            )
                            logger.info(
                                f"[{country_code}] ✓ Cached {question_num}/{total_questions}: {question[:60]}..."
                            )
                            completed = True
                            break
                        last_error = RuntimeError("Empty done_payload from runner")
                    except Exception as inner_exc:
                        last_error = inner_exc

                if not completed:
                    stats["errors"] += 1
                    error_msg = str(last_error) if last_error else "unknown error"
                    raise RuntimeError(
                        f"[{country_code}] Failed question {question_num}/{total_questions} after "
                        f"{max_attempts} attempts: {question[:100]} | {error_msg}"
                    ) from last_error

            except Exception as exc:
                logger.error(
                    f"[{country_code}] Error processing question: {question[:60]}...",
                    exc_info=exc,
                )
                raise

    completion_msg = (
        f"[{country_code}] Preprocessing complete: "
        f"{stats['cache_generated']} generated, "
        f"{stats['cache_hits']} hits, "
        f"{stats['errors']} errors "
        f"(total: {stats['total_questions']} questions)"
    )
    print(completion_msg)
    logger.info(completion_msg)

    return stats


async def run_preprocessing(runner: ChatRunnerProtocol) -> None:
    """
    Run cache preprocessing for all countries in the allowed list.

    Processes all pillar questions for each country in ALLOWED_COUNTRIES.
    For countries without direct documents, uses regional and global documents
    (via list_documents_for_country() which automatically includes regional/GLO docs).

    Args:
        runner: Chat runner instance
    """
    print("=" * 80)
    print("STARTING CACHE PREPROCESSING SERVICE")
    print("=" * 80)
    logger.info("=" * 80)
    logger.info("Starting cache preprocessing service")
    logger.info("=" * 80)

    try:
        # Process all countries from the allowed list
        # list_documents_for_country() will automatically include regional and global documents
        countries = sorted(ALLOWED_COUNTRIES)
        print(f"Processing {len(countries)} countries from allowed list")
        print(f"Countries: {', '.join(countries[:20])}... (showing first 20)")
        logger.info(f"Processing {len(countries)} countries from allowed list")
        logger.info(
            f"Countries: {', '.join(countries[:20])}... (showing first 20 of {len(countries)})"
        )

        total_stats = {
            "total_countries": len(countries),
            "total_questions": 0,
            "total_generated": 0,
            "total_hits": 0,
            "total_errors": 0,
        }

        # Process each country
        for idx, country_code in enumerate(countries, 1):
            country_progress = f"[{idx}/{len(countries)}]"
            print("=" * 80)
            print(f"{country_progress} Processing country: {country_code}")
            print("=" * 80)
            logger.info("=" * 80)
            logger.info(f"{country_progress} Processing country: {country_code}")
            logger.info("=" * 80)

            async with DatabaseSessionManager.session() as session:
                stats = await preprocess_cache_for_country(country_code, runner, session)
                total_stats["total_questions"] += stats["total_questions"]
                total_stats["total_generated"] += stats["cache_generated"]
                total_stats["total_hits"] += stats["cache_hits"]
                total_stats["total_errors"] += stats["errors"]

                # Log country completion with progress
                progress_pct = (idx / len(countries)) * 100
                print(
                    f"{country_progress} {country_code} completed: {stats['cache_generated']} generated, {stats['cache_hits']} hits, {stats['errors']} errors"
                )
                print(f"Overall progress: {idx}/{len(countries)} countries ({progress_pct:.1f}%)")
                logger.info(
                    f"{country_progress} {country_code} completed: "
                    f"{stats['cache_generated']} generated, {stats['cache_hits']} hits, {stats['errors']} errors"
                )
                logger.info(
                    f"Overall progress: {idx}/{len(countries)} countries ({progress_pct:.1f}%)"
                )

        # Final summary
        print("=" * 80)
        print("CACHE PREPROCESSING COMPLETED!")
        print("=" * 80)
        print(f"Countries processed: {total_stats['total_countries']}")
        print(f"Total questions: {total_stats['total_questions']}")
        print(f"Generated: {total_stats['total_generated']}")
        print(f"Cache hits: {total_stats['total_hits']}")
        print(f"Errors: {total_stats['total_errors']}")
        print("=" * 80)
        logger.info("=" * 80)
        logger.info("Cache preprocessing completed!")
        logger.info(f"Countries processed: {total_stats['total_countries']}")
        logger.info(f"Total questions: {total_stats['total_questions']}")
        logger.info(f"Generated: {total_stats['total_generated']}")
        logger.info(f"Cache hits: {total_stats['total_hits']}")
        logger.info(f"Errors: {total_stats['total_errors']}")
        logger.info("=" * 80)

    except Exception as exc:
        print(f"ERROR during cache preprocessing: {exc}")
        logger.exception("Error during cache preprocessing", exc_info=exc)


__all__ = ["ALLOWED_COUNTRIES", "PILLAR_QUESTIONS", "run_preprocessing"]
