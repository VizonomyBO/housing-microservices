from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory

from shared_data_layer.db.models.users import User

class UserFactory(AsyncSQLAlchemyFactory[User]):
    __model__ = User
