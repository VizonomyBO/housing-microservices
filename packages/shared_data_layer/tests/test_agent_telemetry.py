from uuid import uuid4

import pytest
from sqlalchemy import select

from shared_data_layer.db.models.agents import AgentEvent
from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.repositories.agents import AgentTelemetryRepository
from shared_data_layer.testing.factories.agents import AgentRunFactory


@pytest.mark.asyncio
async def test_create_run_defaults_country_from_conversation(db_session):
    conversation = Conversation(owner_user_id=None, country_code="USA")
    db_session.add(conversation)
    await db_session.flush()

    repo = AgentTelemetryRepository(db_session)
    run = await repo.create_run(
        owner_user_id=None,
        conversation_id=conversation.id,
        planner_name="planner.test",
    )

    assert run.conversation_id == conversation.id
    assert run.country_code == "USA"
    assert run.status == "running"


@pytest.mark.asyncio
async def test_append_event_sequences_and_defaults_context(db_session):
    run = await AgentRunFactory.create_async(session=db_session)
    repo = AgentTelemetryRepository(db_session)

    first = await repo.append_event(
        run_id=run.id,
        event_type="planner.start",
        payload={"step": 0},
    )
    second = await repo.append_event(
        run_id=run.id,
        event_type="planner.finish",
        payload={"step": 1},
    )

    assert first.sequence_index == 0
    assert second.sequence_index == 1
    assert second.owner_user_id == run.owner_user_id

    events = await repo.list_events_for_run(run.id)
    assert [event.sequence_index for event in events] == [0, 1]


@pytest.mark.asyncio
async def test_list_runs_filters_by_owner_and_scope(db_session):
    repo = AgentTelemetryRepository(db_session)
    owner_a = uuid4()
    owner_b = uuid4()

    conversation = Conversation(owner_user_id=owner_a, country_code="USA")
    db_session.add(conversation)
    await db_session.flush()

    run_a = await repo.create_run(
        owner_user_id=owner_a,
        conversation_id=conversation.id,
        planner_name="planner.alpha",
    )
    run_b = await repo.create_run(
        owner_user_id=owner_b,
        conversation_id=None,
        planner_name="planner.beta",
        country_code="CAN",
    )
    run_c = await repo.create_run(
        owner_user_id=owner_a,
        conversation_id=None,
        planner_name="planner.gamma",
        country_code="USA",
    )

    owner_runs = await repo.list_runs(owner_user_id=owner_a)
    assert {r.id for r in owner_runs} == {run_a.id, run_c.id}

    canada_runs = await repo.list_runs(country_code="CAN")
    assert len(canada_runs) == 1
    assert canada_runs[0].id == run_b.id

    convo_runs = await repo.list_runs(conversation_id=conversation.id)
    assert len(convo_runs) == 1
    assert convo_runs[0].id == run_a.id

    all_runs = await repo.list_runs(limit=10)
    assert len(all_runs) >= 3


@pytest.mark.asyncio
async def test_get_run_with_events_returns_pydantic(db_session):
    run = await AgentRunFactory.create_async(session=db_session)
    repo = AgentTelemetryRepository(db_session)
    await repo.append_event(run_id=run.id, event_type="planner.start", payload={})
    await repo.append_event(run_id=run.id, event_type="planner.finish", payload={})

    run_with_events = await repo.get_run_with_events(run.id)
    assert run_with_events is not None
    assert len(run_with_events.events) == 2
    assert run_with_events.events[0].event_type == "planner.start"


@pytest.mark.asyncio
async def test_deleting_run_cascades_events(db_session):
    run = await AgentRunFactory.create_async(session=db_session)
    repo = AgentTelemetryRepository(db_session)
    await repo.append_event(run_id=run.id, event_type="planner.start", payload={})

    deleted = await repo.delete(run.id)
    assert deleted is True

    stmt = select(AgentEvent).where(AgentEvent.run_id == run.id)
    result = await db_session.execute(stmt)
    assert result.scalars().all() == []
