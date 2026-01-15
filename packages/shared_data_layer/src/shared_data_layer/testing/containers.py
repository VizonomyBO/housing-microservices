from testcontainers.core.wait_strategies import ExecWaitStrategy, LogMessageWaitStrategy
from testcontainers.postgres import PostgresContainer


class PostgresContainerWithVector(PostgresContainer):
    def __init__(self, image="pgvector/pgvector:pg16", **kwargs):
        super().__init__(
            image=image, tmpfs={"/var/lib/postgresql/data": "rw"}, **kwargs
        )
        self.with_command(
            "postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off"
        )
        # Use structured wait strategy instead of deprecated decorator
        self.wait_strategy = LogMessageWaitStrategy(
            "database system is ready to accept connections"
        )
        self.waiting_for(self.wait_strategy)

    def _connect(self) -> None:
        # Replace parent @wait_container_is_ready decorator with explicit wait strategy
        escaped_password = self.password.replace("'", "'\"'\"'")
        ExecWaitStrategy(
            [
                "sh",
                "-c",
                f"PGPASSWORD='{escaped_password}' psql --username {self.username} "
                f"--dbname {self.dbname} --host 127.0.0.1 -c 'select version();'",
            ]
        ).wait_until_ready(self)

    def get_connection_url(self, host=None, driver="asyncpg"):
        return super().get_connection_url(host=host, driver=driver)
