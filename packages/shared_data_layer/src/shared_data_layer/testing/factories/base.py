from typing import Generic, TypeVar

from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession

from shared_data_layer.db.base import Base

T = TypeVar("T", bound=Base)


class AsyncSQLAlchemyFactory(Generic[T], SQLAlchemyFactory[T]):
    __is_base_factory__ = True

    @classmethod
    async def create_async(cls, session: AsyncSession, **kwargs):  # type: ignore
        instance = cls.build(**kwargs)
        session.add(instance)
        await session.flush()
        await session.refresh(instance)
        return instance

    @classmethod
    def get_sqlalchemy_types(cls):
        from pgvector.sqlalchemy import Vector

        types = super().get_sqlalchemy_types()
        types[Vector] = list[float]
        return types
