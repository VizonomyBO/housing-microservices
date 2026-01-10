"""Cache preprocessing service for pillar questions."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.agent.runner import ChatRunnerProtocol
from agent_api.auth.validator import AuthContext
from agent_api.http.context import RequestContext
from agent_api.http.schemas import BlockingChatResponse, ChatMessagePayload, ChatRequestBody, ResponseMode
from agent_api.http.streaming import run_blocking_chat
from agent_api.models.chat import ChatRequestContext
from agent_api.services.cache import ChatCacheService
from shared_data_layer.db.models import Document
from shared_data_layer.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)

# Pillar Questions - 47 total questions across 5 pillars
PILLAR_QUESTIONS = {
    "Sector Context": [
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
    "Policies and Institutions": [
        "Who are the main institutions responsible for housing, and what are their mandates, capacities, and constraints?",
        "What is the legal framework governing the housing sector and what potential gaps or weaknesses exist?",
        "What is the legal and regulatory framework for rental housing, including taxation and eviction procedures?",
        "What role do sub-national governments play in housing policy, program design, and delivery, and how effective are they?",
        "What are the financial and operational constraints of local municipalities in delivering serviced land?",
        "How sustainable are municipal financing models, especially for land servicing, cost recovery, and tariffs?",
        "What is the capacity of local governments to partner with private developers for infrastructure provision?",
        "What are the key policy and institutional constraints affecting the housing sector?",
    ],
    "Government Programs": [
        "What is the chronology of government interventions in the housing sector, and what have been the successes and failures?",
        "What role do social and public housing programs play, and how financially sustainable are they?",
        "What are the design, coverage, eligibility criteria, and performance of government housing programs in the last 10 years?",
        "What are the main constraints to upgrading informal settlements, including affordability, tenure insecurity, and service gaps?",
        "What are the key strengths and weaknesses of government programs to support affordable housing?",
    ],
    "Supply Chain": [
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
    "Finance": [
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
        stmt = (
            select(Document.country_code)
            .where(Document.status == "active")
            .distinct()
        )
        result = await session.execute(stmt)
        countries = [row[0] for row in result.fetchall() if row[0]]
        return sorted(countries)


async def preprocess_cache_for_country(
    country_code: str,
    runner: ChatRunnerProtocol,
    db_session: AsyncSession,
) -> dict[str, Any]:
    """
    Preprocess cache for all pillar questions for a given country.

    Args:
        country_code: ISO-3 country code
        runner: Chat runner instance
        db_session: Database session

    Returns:
        Dictionary with statistics about the preprocessing
    """
    cache_service = ChatCacheService(db_session)
    stats = {
        "country_code": country_code,
        "total_questions": 0,
        "cache_hits": 0,
        "cache_generated": 0,
        "errors": 0,
    }

    logger.info(f"Starting cache preprocessing for country: {country_code}")

    for pillar_name, questions in PILLAR_QUESTIONS.items():
        for question in questions:
            stats["total_questions"] += 1

            try:
                # Check if cache already exists
                cached = await cache_service.get_cached_response(country_code, question)
                if cached:
                    stats["cache_hits"] += 1
                    logger.debug(
                        f"[{country_code}] Cache hit for: {question[:50]}..."
                    )
                    continue

                # Generate response
                logger.info(
                    f"[{country_code}] Generating response for: {question[:60]}..."
                )

                # Create a minimal auth context (system/internal)
                auth = AuthContext(
                    user_id=None,
                    tenant_id=None,
                    scopes=set(),
                    claims={},
                )

                # Create request context
                request_context = RequestContext(
                    request_id=f"preprocess-{country_code}-{stats['total_questions']}",
                    user_agent=None,
                    client_ip=None,
                )

                # Create chat request
                chat_request = ChatRequestContext(
                    conversation_id=f"preprocess-{country_code}",
                    thread_id=f"preprocess-{country_code}",
                    session_id=None,
                    allow_stateless=True,
                    message=ChatMessagePayload(content=question),
                    hints={},
                    constraints={"country_code": country_code},
                    owner_user_id=None,
                    workspace_id=None,
                    tenant_id=None,
                )

                # Run chat (this will fail if no documents attached - that's expected)
                # We'll need to handle this gracefully
                try:
                    result = await runner.run_chat(
                        request=chat_request,
                        auth=auth,
                        request_context=request_context,
                        sse_emitter=None,
                        prompt_overrides={},
                        hints={},
                        response_mode=ResponseMode.BLOCKING,
                        db_session=db_session,
                    )

                    if result and result.done_payload:
                        # Store in cache
                        response_data = {
                            "thread_id": chat_request.thread_id,
                            "request_id": request_context.request_id,
                            "done": result.done_payload,
                            "messages": result.messages or [],
                        }
                        await cache_service.store_response(
                            country_code, question, response_data
                        )
                        stats["cache_generated"] += 1
                        logger.info(
                            f"[{country_code}] ✓ Cached response for: {question[:60]}..."
                        )
                except Exception as inner_exc:
                    # Expected errors like "no documents attached" - skip
                    logger.warning(
                        f"[{country_code}] Skipping question (likely no docs attached): {str(inner_exc)[:100]}"
                    )
                    stats["errors"] += 1

            except Exception as exc:
                logger.error(
                    f"[{country_code}] Error processing question: {question[:60]}...",
                    exc_info=exc,
                )
                stats["errors"] += 1

    logger.info(
        f"[{country_code}] Preprocessing complete: "
        f"{stats['cache_generated']} generated, "
        f"{stats['cache_hits']} hits, "
        f"{stats['errors']} errors"
    )

    return stats


async def run_preprocessing(runner: ChatRunnerProtocol) -> None:
    """
    Run cache preprocessing for all countries with documents.

    Args:
        runner: Chat runner instance
    """
    logger.info("=" * 80)
    logger.info("Starting cache preprocessing service")
    logger.info("=" * 80)

    try:
        # Get countries with documents
        countries = await get_countries_with_documents()
        logger.info(f"Found {len(countries)} countries with active documents: {countries}")

        if not countries:
            logger.info("No countries with documents found. Skipping preprocessing.")
            return

        total_stats = {
            "total_countries": len(countries),
            "total_questions": 0,
            "total_generated": 0,
            "total_hits": 0,
            "total_errors": 0,
        }

        # Process each country
        for country_code in countries:
            async with DatabaseSessionManager.session() as session:
                stats = await preprocess_cache_for_country(
                    country_code, runner, session
                )
                total_stats["total_questions"] += stats["total_questions"]
                total_stats["total_generated"] += stats["cache_generated"]
                total_stats["total_hits"] += stats["cache_hits"]
                total_stats["total_errors"] += stats["errors"]

        # Final summary
        logger.info("=" * 80)
        logger.info("Cache preprocessing completed!")
        logger.info(f"Countries processed: {total_stats['total_countries']}")
        logger.info(f"Total questions: {total_stats['total_questions']}")
        logger.info(f"Generated: {total_stats['total_generated']}")
        logger.info(f"Cache hits: {total_stats['total_hits']}")
        logger.info(f"Errors: {total_stats['total_errors']}")
        logger.info("=" * 80)

    except Exception as exc:
        logger.exception("Error during cache preprocessing", exc_info=exc)


__all__ = ["run_preprocessing", "PILLAR_QUESTIONS"]
