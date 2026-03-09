#!/usr/bin/env python3
"""
Verify chat response cache for given countries: counts and short/missing answers.

Checks that each cached response has an answer of at least MIN_ANSWER_CHARS (default 150).
Use after regeneration to ensure no empty or placeholder-only entries.

Usage (from repo root with DATABASE_URL set, e.g. via tunnel):
  cd services/agent-api && uv run python scripts/validate_country_cache.py MEX IDN PAK ZAF ARG BOL TUR MOZ
"""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict

from shared_data_layer.db.models import ChatResponseCache
from shared_data_layer.db.session import DatabaseSessionManager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

MIN_ANSWER_CHARS = 150

TARGET_COUNTRIES = ["MEX", "IDN", "PAK", "ZAF", "ARG", "BOL", "TUR", "MOZ"]


def get_answer_length(response: dict) -> int:
    done = response.get("done") if isinstance(response, dict) else None
    if done is None:
        return 0
    answer = done.get("answer") if isinstance(done, dict) else None
    if answer is None:
        return 0
    return len(str(answer).strip())


async def validate_countries(session: AsyncSession, country_codes: list[str]) -> dict:
    stmt = select(ChatResponseCache).where(
        ChatResponseCache.country_code.in_([c.upper() for c in country_codes])
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    by_country: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for row in rows:
        length = get_answer_length(row.response)
        by_country[row.country_code].append((row.question[:80], length))

    return dict(by_country)


def main_sync(country_codes: list[str], database_url: str) -> None:
    DatabaseSessionManager.init(database_url)

    async def run() -> None:
        async with DatabaseSessionManager.session() as session:
            by_country = await validate_countries(session, country_codes)
        expected_per_country = 50
        all_ok = True
        for code in sorted(country_codes):
            code = code.upper()
            entries = by_country.get(code, [])
            total = len(entries)
            short = [(q, n) for q, n in entries if n < MIN_ANSWER_CHARS]
            ok_count = total - len(short)
            status = "OK" if total >= expected_per_country and not short else "ISSUES"
            if short or total < expected_per_country:
                all_ok = False
            print(
                f"{code}: {status}  total={total}/50  ok(>={MIN_ANSWER_CHARS} chars)={ok_count}  short={len(short)}"
            )
            for q, n in short[:5]:
                print(f"  - {n} chars: {q}...")
            if len(short) > 5:
                print(f"  ... and {len(short) - 5} more short/missing")
        if all_ok:
            print("All countries have 50 entries with answers >= 150 characters.")
        else:
            print("Some countries have missing or short answers (see above).")
            sys.exit(1)

    asyncio.run(run())


if __name__ == "__main__":
    import os

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)
    codes = [c.strip().upper() for c in (sys.argv[1:] if len(sys.argv) > 1 else TARGET_COUNTRIES)]
    if not codes:
        codes = TARGET_COUNTRIES
    main_sync(codes, database_url)
