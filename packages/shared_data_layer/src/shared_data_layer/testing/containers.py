from testcontainers.postgres import PostgresContainer


class PostgresContainerWithVector(PostgresContainer):
    def __init__(self, image="pgvector/pgvector:pg16", **kwargs):
        super().__init__(
            image=image, tmpfs={"/var/lib/postgresql/data": "rw"}, **kwargs
        )
        self.with_command(
            "postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off"
        )

    def get_connection_url(self, host=None, driver="asyncpg"):
        return super().get_connection_url(host=host, driver=driver)
