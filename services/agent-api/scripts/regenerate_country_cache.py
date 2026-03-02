#!/usr/bin/env python3
"""
Regenerate chat response cache for specific countries.

Clears existing cache entries for each country, then runs preprocessing
(pillar questions with retrieval_profile=country_profile) to repopulate
the cache. Use after updating documents or model behavior.

Usage (from repo root with env loaded):
  env_file=$(scripts/use_env.sh local); set -a && source "$env_file" && set +a
  cd services/agent-api && uv run python scripts/regenerate_country_cache.py BOL ARG MOZ TUR

Or from services/agent-api with DATABASE_URL etc. set:
  uv run python scripts/regenerate_country_cache.py BOL ARG MOZ TUR
"""

from __future__ import annotations

import asyncio
import sys

from shared_data_layer.db.session import DatabaseSessionManager

from agent_api.agent.runner import LangGraphRunner
from agent_api.services.cache import ChatCacheService
from agent_api.services.preprocessing import preprocess_cache_for_country
from agent_api.settings import load_settings


async def main(country_codes: list[str]) -> int:
    settings = load_settings()
    if not settings.database_url:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        return 1

    DatabaseSessionManager.init(settings.database_url)
    runner = LangGraphRunner(settings=settings)
    total_errors = 0
    failed_countries: list[str] = []

    for country_code in country_codes:
        code = country_code.strip().upper()
        if len(code) != 3:
            print(f"SKIP invalid code: {country_code!r}", file=sys.stderr)
            continue
        print("=" * 60)
        print(f"Regenerating cache for {code}")
        print("=" * 60)
        try:
            async with DatabaseSessionManager.session() as session:
                cache_service = ChatCacheService(session)
                deleted = await cache_service.clear_cache_for_country(code)
                print(f"Cleared {deleted} existing cache entries for {code}")
                stats = await preprocess_cache_for_country(
                    code, runner, session, force_regenerate=True
                )
                total_errors += stats["errors"]
                if stats["errors"] > 0:
                    failed_countries.append(code)
                    failed_examples = ", ".join(q[:60] for q in stats["failed_questions"][:3])
                    print(
                        f"Preprocessing {code}: {stats['cache_generated']} generated, "
                        f"{stats['cache_hits']} hits, {stats['errors']} errors "
                        f"(examples: {failed_examples})"
                    )
                else:
                    print(
                        f"Preprocessing {code}: {stats['cache_generated']} generated, "
                        f"{stats['cache_hits']} hits, {stats['errors']} errors"
                    )
        except Exception as exc:
            if isinstance(exc, (asyncio.CancelledError, TimeoutError, OSError)):
                raise
            total_errors += 1
            failed_countries.append(code)
            print(
                f"ERROR: {code} regeneration failed: {type(exc).__name__}: {exc}", file=sys.stderr
            )

    if total_errors > 0:
        print(
            f"Done with {total_errors} error(s) across countries: {', '.join(failed_countries)}",
            file=sys.stderr,
        )
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default: Bolivia, Argentina, Mozambique, Turkey
        codes = ["BOL", "ARG", "MOZ", "TUR"]
        print(f"No country codes provided; using: {codes}", file=sys.stderr)
    else:
        codes = [c.upper() for c in sys.argv[1:]]
    try:
        raise SystemExit(asyncio.run(main(codes)))
    except (asyncio.CancelledError, TimeoutError, OSError) as e:
        print(
            "ERROR: Cannot reach the database (timeout or connection refused).\n"
            "  - For prod, run this script on EC2 (e.g. docker exec into agent-api)\n"
            "    or ensure DATABASE_URL is reachable (VPN/tunnel).",
            file=sys.stderr,
        )
        raise SystemExit(1) from e
