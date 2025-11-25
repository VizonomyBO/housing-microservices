import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
class AsyncBaseTestCase:
    @pytest.fixture(autouse=True)
    def setup_session(self, db_session: AsyncSession):
        self.session = db_session
