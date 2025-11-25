from testcontainers.postgres import PostgresContainer

class PostgresContainerWithVector(PostgresContainer):
    def __init__(self, image="pgvector/pgvector:pg16", **kwargs):
        super().__init__(image=image, **kwargs)

    def get_connection_url(self, driver="asyncpg"):
        return super().get_connection_url(driver=driver)
