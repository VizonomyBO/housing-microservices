import argparse
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from shared_data_layer.config.settings import settings


def main():
    parser = argparse.ArgumentParser(description="Shared Data Layer Management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations")
    migrate_parser.add_argument("--revision", default="head", help="Revision to upgrade to (default: head)")

    args = parser.parse_args()

    if args.command == "migrate":
        run_migrations(args.revision)
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


if __name__ == "__main__":
    main()
