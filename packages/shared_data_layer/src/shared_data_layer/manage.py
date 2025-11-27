import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config

from shared_data_layer.config.settings import settings
from shared_data_layer.db.maintenance import (
    refresh_graph_community_rollups,
    refresh_graph_materializations,
)
from shared_data_layer.db.session import DatabaseSessionManager


def main():
    parser = argparse.ArgumentParser(description="Shared Data Layer Management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations")
    migrate_parser.add_argument(
        "--revision", default="head", help="Revision to upgrade to (default: head)"
    )

    refresh_parser = subparsers.add_parser(
        "refresh-graph-mviews",
        help="Refresh knowledge-graph materialized views after bulk ingestion",
    )
    refresh_parser.add_argument(
        "--concurrently",
        action="store_true",
        help="Use CONCURRENTLY to keep the views available (requires unique indexes)",
    )

    community_parser = subparsers.add_parser(
        "refresh-graph-communities",
        help="Recompute graph community rollups for a given scope",
    )
    community_parser.add_argument(
        "--country-code",
        dest="country_code",
        help="Optional ISO alpha-3 country filter",
    )
    community_parser.add_argument(
        "--algo-version",
        dest="algo_version",
        help="Optional algorithm version to target",
    )
    community_parser.add_argument(
        "--community-id",
        dest="community_id",
        help="Refresh a single community by UUID",
    )

    args = parser.parse_args()

    if args.command == "migrate":
        run_migrations(args.revision)
    elif args.command == "refresh-graph-mviews":
        asyncio.run(run_refresh_graph_mviews(args.concurrently))
    elif args.command == "refresh-graph-communities":
        asyncio.run(
            run_refresh_graph_communities(
                args.country_code, args.algo_version, args.community_id
            )
        )
    else:
        parser.print_help()


def run_migrations(revision: str):
    """Run Alembic migrations programmatically."""
    # Assume the alembic.ini is in the migrations directory
    package_dir = Path(__file__).parent
    migrations_dir = package_dir / "migrations"
    alembic_ini_path = migrations_dir / "alembic.ini"

    if not alembic_ini_path.exists():
        print(f"Error: alembic.ini not found at {alembic_ini_path}")
        sys.exit(1)

    # Create Alembic Config
    alembic_cfg = Config(str(alembic_ini_path))

    # Set script location explicitly to absolute path
    alembic_cfg.set_main_option("script_location", str(migrations_dir))

    # Set sqlalchemy.url from settings
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

    print(f"Running migrations to {revision}...")
    try:
        command.upgrade(alembic_cfg, revision)
        print("Migrations completed successfully.")
    except Exception as e:
        print(f"Error running migrations: {e}")
        sys.exit(1)


async def run_refresh_graph_mviews(concurrently: bool) -> None:
    """Initialize an async session and refresh graph materialized views."""
    DatabaseSessionManager.init(settings.DATABASE_URL)
    try:
        async with DatabaseSessionManager.session() as session:
            await refresh_graph_materializations(session, concurrently=concurrently)
            await session.commit()
    finally:
        await DatabaseSessionManager.dispose()
    mode = "CONCURRENTLY" if concurrently else "non-concurrently"
    print(f"Graph materialized views refreshed ({mode}).")


async def run_refresh_graph_communities(
    country_code: str | None, algo_version: str | None, community_id: str | None
) -> None:
    """Wire up the rollup helper to the CLI."""

    DatabaseSessionManager.init(settings.DATABASE_URL)
    parsed_country = country_code.upper() if country_code else None
    parsed_id = UUID(community_id) if community_id else None
    try:
        async with DatabaseSessionManager.session() as session:
            await refresh_graph_community_rollups(
                session,
                country_code=parsed_country,
                algo_version=algo_version,
                community_id=parsed_id,
            )
            await session.commit()
    finally:
        await DatabaseSessionManager.dispose()

    scope_bits = ["communities"]
    if parsed_country:
        scope_bits.append(f"country={parsed_country}")
    if algo_version:
        scope_bits.append(f"algo={algo_version}")
    if parsed_id:
        scope_bits.append(f"id={parsed_id}")
    scope = " | ".join(scope_bits)
    print(f"Graph community rollups refreshed ({scope}).")


if __name__ == "__main__":
    main()
