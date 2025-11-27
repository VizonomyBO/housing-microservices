from uuid import uuid4

from polyfactory import Use

from shared_data_layer.db.models.agents import AgentEvent, AgentRun
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory


class AgentRunFactory(AsyncSQLAlchemyFactory[AgentRun]):
    __model__ = AgentRun
    __set_relationships__ = False

    owner_user_id = Use(uuid4)
    conversation_id = Use(lambda: None)
    planner_name = Use(lambda: "planner.basic")
    planner_version = Use(lambda: "v1")
    status = Use(lambda: "running")
    country_code = Use(lambda: "USA")
    input_prompt = Use(lambda: "Plan the next action")
    document_scope = Use(lambda: {"country_code": "USA"})
    metadata_ = Use(lambda: {"task": "demo"})

    @classmethod
    async def create_async(  # type: ignore[override]
        cls,
        session,
        *,
        conversation=None,
        **kwargs,
    ):
        if conversation is not None:
            kwargs.setdefault("conversation_id", conversation.id)
            if conversation.country_code and "country_code" not in kwargs:
                kwargs["country_code"] = conversation.country_code
        return await super().create_async(session=session, **kwargs)


class AgentEventFactory(AsyncSQLAlchemyFactory[AgentEvent]):
    __model__ = AgentEvent
    __set_relationships__ = False

    event_type = Use(lambda: "log")
    payload = Use(lambda: {"message": "ok"})
    sequence_index = Use(lambda: 0)

    @classmethod
    async def create_async(  # type: ignore[override]
        cls,
        session,
        *,
        run=None,
        **kwargs,
    ):
        run_obj = run
        if run_obj is None and "run_id" not in kwargs:
            run_obj = await AgentRunFactory.create_async(session=session)
        if run_obj is not None:
            kwargs.setdefault("run_id", run_obj.id)
            kwargs.setdefault("owner_user_id", run_obj.owner_user_id)
            kwargs.setdefault("country_code", run_obj.country_code)
        return await super().create_async(session=session, **kwargs)
