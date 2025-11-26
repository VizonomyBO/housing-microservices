from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from shared_data_layer.config.settings import settings
from shared_data_layer.testing.containers import PostgresContainerWithVector


def test_generate_migration():
    """
    Starts a Postgres container and generates an Alembic migration
    based on the current model definitions.
    """
    with PostgresContainerWithVector() as postgres:
        # Get connection URL (asyncpg is default in container,
        # but alembic uses sync driver usually?
        # Actually env.py uses async_engine_from_config, so it expects an async url)
        # However, for the *initial* connection check or if we were using sync alembic,
        # we might need sync. But our env.py is async.

        db_url = postgres.get_connection_url(driver="asyncpg")

        # Monkeypatch settings so env.py picks up the container URL
        settings.DATABASE_URL = db_url

        # Setup paths
        base_dir = Path(__file__).parent.parent
        migrations_dir = base_dir / "src" / "shared_data_layer" / "migrations"
        alembic_ini_path = migrations_dir / "alembic.ini"
        versions_dir = migrations_dir / "versions"

        assert alembic_ini_path.exists(), f"alembic.ini not found at {alembic_ini_path}"

        # Count existing migrations
        existing_versions = list(versions_dir.glob("*.py"))
        initial_count = len(existing_versions)

        # Configure Alembic
        alembic_cfg = Config(str(alembic_ini_path))
        alembic_cfg.set_main_option("script_location", str(migrations_dir))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        # Run revision --autogenerate
        print(f"Generating migration connected to {db_url}...", flush=True)

        # Ensure we don't drop into PDB
        import os

        os.environ["PYTHONBREAKPOINT"] = "0"

        # We wrap this in a try/except to print output if it fails
        try:
            # Upgrade to head first so we have a base to compare against
            print("Upgrading database to head...", flush=True)
            command.upgrade(alembic_cfg, "head")

            # We need to run this in a sync context, but command.revision is sync.
            # The env.py will handle the async engine creation.
            command.revision(
                alembic_cfg, message="align_models_with_design", autogenerate=True
            )
            print("Alembic revision command completed.", flush=True)
        except Exception as e:
            import traceback

            traceback.print_exc()
            pytest.fail(f"Alembic revision failed: {e}")

        # Verify a new file was created
        new_versions = list(versions_dir.glob("*.py"))
        if len(new_versions) == initial_count + 1:
            new_file = set(new_versions) - set(existing_versions)
            print(f"Created migration file: {new_file.pop()}", flush=True)
        else:
            print(
                f"Existing versions: {[f.name for f in existing_versions]}", flush=True
            )
            print(f"New versions: {[f.name for f in new_versions]}", flush=True)
            pytest.fail("No new migration file created")
