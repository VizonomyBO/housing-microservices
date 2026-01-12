from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared_data_layer.config.settings import settings
from shared_data_layer.db.models.documents import Document
from shared_data_layer.db.session import DatabaseSessionManager
from shared_data_layer.utils.publication_year import (
    coerce_publication_year,
    extract_years_from_text,
    normalize_metadata_publication_year,
)

logger = logging.getLogger(__name__)

CHUNK_YEAR_SQL = text(
    """
    SELECT DISTINCT
        CAST(
            substring(text_content FROM '(1[5-9]\\d{2}|20\\d{2}|21\\d{2})')
            AS INT
        ) AS year
    FROM (
        SELECT text_content
        FROM chunks
        WHERE document_id = :document_id
          AND text_content IS NOT NULL
        ORDER BY position
        LIMIT :chunk_limit
    ) AS limited
    WHERE substring(text_content FROM '(1[5-9]\\d{2}|20\\d{2}|21\\d{2})') IS NOT NULL
    """
)


@dataclass
class BackfillStats:
    scanned: int = 0
    updated: int = 0
    skipped_existing: int = 0
    skipped_missing: int = 0
    skipped_ambiguous: int = 0
    invalid_values: int = 0
    chunk_search_used: int = 0

    def as_dict(self) -> dict[str, int]:
        return self.__dict__.copy()

    def __str__(self) -> str:  # pragma: no cover - pretty-print
        return (
            "scanned={scanned} updated={updated} "
            "existing={skipped_existing} missing={skipped_missing} "
            "ambiguous={skipped_ambiguous} invalid={invalid_values} "
            "chunk_search_used={chunk_search_used}"
        ).format(**self.as_dict())


def _configure_logging(log_file: Path | None, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)


def _candidate_texts(document: Document) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if document.canonical_name:
        items.append(("canonical_name", document.canonical_name))
    if document.source_uri:
        items.append(("source_uri", document.source_uri))
        parsed = urlparse(document.source_uri)
        if parsed.path:
            path_part = Path(parsed.path)
            stem_or_path = path_part.name or parsed.path
            items.append(("source_uri_path", str(stem_or_path)))
    return items


def _pick_year_from_sources(
    sources: Iterable[tuple[int, str]],
) -> tuple[int | None, set[int], set[str]]:
    seen_years: set[int] = set()
    contributing_sources: set[str] = set()
    chosen: int | None = None
    for year, label in sources:
        seen_years.add(year)
        if chosen is None:
            chosen = year
        contributing_sources.add(label)
    return chosen if len(seen_years) == 1 else None, seen_years, contributing_sources


async def _chunk_year_candidates(
    session: AsyncSession, document_id: UUID, chunk_limit: int
) -> list[int]:
    result = await session.execute(
        CHUNK_YEAR_SQL, {"document_id": document_id, "chunk_limit": chunk_limit}
    )
    rows = result.scalars().all()
    candidates: list[int] = []
    for raw in rows:
        year = coerce_publication_year(raw)
        if year is not None:
            candidates.append(year)
    return candidates


async def _derive_publication_year(
    session: AsyncSession,
    document: Document,
    *,
    chunk_scan_limit: int,
    skip_text_search: bool,
) -> tuple[int | None, set[int], set[str], bool]:
    """Return (year, candidate_years, sources, used_chunk_search)."""

    candidates: list[tuple[int, str]] = []
    for label, text_value in _candidate_texts(document):
        normalized_value = str(text_value)
        for year in extract_years_from_text(normalized_value):
            candidates.append((year, label))

    used_chunk_search = False
    if not candidates and not skip_text_search:
        chunk_years = await _chunk_year_candidates(
            session, document.id, chunk_scan_limit
        )
        if chunk_years:
            used_chunk_search = True
            for year in chunk_years:
                candidates.append((year, "chunk_text"))

    chosen, seen_years, sources = _pick_year_from_sources(candidates)
    return chosen, seen_years, sources, used_chunk_search


async def backfill_publication_years(
    session: AsyncSession,
    *,
    apply_changes: bool,
    limit: int | None,
    skip_text_search: bool,
    chunk_scan_limit: int,
) -> BackfillStats:
    stats = BackfillStats()

    stmt = select(Document).where(Document.deleted_at.is_(None))
    stmt = stmt.order_by(Document.created_at)
    if limit:
        stmt = stmt.limit(limit)

    stream = await session.stream_scalars(stmt)
    async for document in stream:
        stats.scanned += 1
        raw_metadata = (
            document.metadata_ if isinstance(document.metadata_, dict) else {}
        )
        existing_raw = (
            raw_metadata.get("publication_year")
            if isinstance(raw_metadata, dict)
            else None
        )
        metadata, existing_year, provided = normalize_metadata_publication_year(
            raw_metadata
        )
        if existing_year is not None:
            if existing_raw != existing_year:
                stats.updated += 1
                logger.info(
                    "%s publication_year for %s to %s (was %r)",
                    "Normalized" if apply_changes else "Would normalize",
                    document.id,
                    existing_year,
                    existing_raw,
                )
                if apply_changes:
                    metadata["publication_year"] = existing_year
                    document.metadata_ = metadata
                    await session.flush()
            else:
                stats.skipped_existing += 1
            continue
        if provided and existing_year is None:
            stats.invalid_values += 1
            logger.warning(
                "Invalid publication_year metadata for %s (value=%r); attempting "
                "derivation",
                document.id,
                existing_raw,
            )

        year, candidates, sources, used_chunk_search = await _derive_publication_year(
            session,
            document,
            chunk_scan_limit=chunk_scan_limit,
            skip_text_search=skip_text_search,
        )
        if used_chunk_search:
            stats.chunk_search_used += 1

        if not candidates:
            stats.skipped_missing += 1
            logger.info(
                "No publication year derived for %s (%s)",
                document.id,
                document.canonical_name,
            )
            continue
        if year is None:
            stats.skipped_ambiguous += 1
            logger.warning(
                "Ambiguous publication years for %s: %s",
                document.id,
                sorted(candidates),
            )
            continue

        metadata["publication_year"] = year
        if apply_changes:
            document.metadata_ = metadata
            await session.flush()
        stats.updated += 1
        logger.info(
            "Set publication_year=%s for %s via %s",
            year,
            document.id,
            ",".join(sorted(sources)) if sources else "unknown",
        )

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill publication_year metadata based on filenames/URIs",
    )
    parser.add_argument(
        "--database-url",
        default=settings.DATABASE_URL,
        help="SQLAlchemy URL for housing DB (default: %(default)s)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes (default: dry-run)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional limit on documents to scan",
    )
    parser.add_argument(
        "--skip-text-search",
        action="store_true",
        help="Skip chunk text fallback search (filename/URI only)",
    )
    parser.add_argument(
        "--chunk-scan-limit",
        type=int,
        default=5,
        help="How many earliest chunks to scan when searching text for a year",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Optional path to write detailed logs (appends if exists)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()
    if args.chunk_scan_limit < 1:
        parser.error("--chunk-scan-limit must be >= 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1 when provided")
    return args


async def async_main() -> BackfillStats:
    args = parse_args()
    _configure_logging(args.log_file, args.verbose)

    logger.info(
        "Starting publication_year backfill "
        "(apply=%s, skip_text_search=%s, chunk_limit=%s)",
        args.apply,
        args.skip_text_search,
        args.chunk_scan_limit,
    )

    DatabaseSessionManager.init(args.database_url)
    try:
        async with DatabaseSessionManager.session() as session:
            stats = await backfill_publication_years(
                session,
                apply_changes=args.apply,
                limit=args.limit,
                skip_text_search=args.skip_text_search,
                chunk_scan_limit=args.chunk_scan_limit,
            )
            if args.apply:
                await session.commit()
            else:
                await session.rollback()
            logger.info("Backfill complete: %s", stats)
            return stats
    finally:
        await DatabaseSessionManager.dispose()


def main() -> None:  # pragma: no cover - CLI entrypoint
    asyncio.run(async_main())


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
