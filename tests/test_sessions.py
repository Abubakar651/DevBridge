import asyncio
import copy
import uuid

import pytest

from server.errors import AppError
from server.sessions import PracticeStore
from conftest import FakeProvider, ANSWER


def key():
    return str(uuid.uuid4())


@pytest.mark.anyio
async def test_full_cycle_and_retry_keep_facts_but_separate_attempts(context):
    store, provider = PracticeStore(), FakeProvider()
    session_id = store.create(context, key())["sessionId"]
    await store.advance(session_id, key(), provider)
    store.answer(session_id, ANSWER, key())
    await store.advance(session_id, key(), provider)
    store.finish(session_id, key())
    first = await store.advance(session_id, key(), provider)
    assert first["attempts"][0]["feedback"]
    retry = store.retry(session_id, key())
    assert retry["context"] == first["context"]
    assert retry["attempts"][1]["messages"] == []
    await store.advance(session_id, key(), provider)
    store.answer(session_id, "Search is ready. I recommend deciding scope before adding export.", key())
    store.finish(session_id, key())
    second = await store.advance(session_id, key(), provider)
    assert provider.coach_calls[1][2] == first["attempts"][0]["messages"]
    assert second["attempts"][1]["feedback"]["comparison"]


@pytest.mark.anyio
async def test_idempotent_create_answers_and_advances_cannot_duplicate_turns(context):
    store, provider = PracticeStore(), FakeProvider()
    create_id, advance_id, answer_id = key(), key(), key()
    session_id = store.create(context, create_id)["sessionId"]
    assert store.create(context, create_id)["sessionId"] == session_id
    await store.advance(session_id, advance_id, provider)
    await store.advance(session_id, advance_id, provider)
    assert len(provider.roleplay_calls) == 1
    store.answer(session_id, ANSWER, answer_id)
    store.answer(session_id, ANSWER, answer_id)
    assert store.get(session_id).answers == 1
    with pytest.raises(AppError, match="reused"):
        store.answer(session_id, "A different message", answer_id)


@pytest.mark.anyio
async def test_three_answers_transition_to_coaching_in_python(context):
    store, provider = PracticeStore(), FakeProvider()
    session_id = store.create(context, key())["sessionId"]
    await store.advance(session_id, key(), provider)
    for _ in range(3):
        store.answer(session_id, ANSWER, key())
        await store.advance(session_id, key(), provider)
    practice = store.get(session_id)
    assert practice.answers == 3
    assert practice.attempt.feedback
    assert len(provider.roleplay_calls) == 3
    assert len(provider.coach_calls) == 1
    with pytest.raises(AppError):
        store.answer(session_id, "A fourth answer", key())


@pytest.mark.anyio
async def test_failed_follow_up_retries_without_resubmitting_an_answer(context):
    store, provider = PracticeStore(), FakeProvider()
    session_id = store.create(context, key())["sessionId"]
    await store.advance(session_id, key(), provider)
    store.answer(session_id, ANSWER, key())
    original = provider.roleplay
    async def failure(*args):
        raise AppError(503, "Temporarily busy", "PROVIDER_BUSY")
    provider.roleplay = failure
    advance_id = key()
    with pytest.raises(AppError):
        await store.advance(session_id, advance_id, provider)
    provider.roleplay = original
    await store.advance(session_id, advance_id, provider)
    assert store.get(session_id).answers == 1
    assert [turn["role"] for turn in store.get(session_id).attempt.messages] == ["assistant", "user", "assistant"]


@pytest.mark.anyio
async def test_stop_discards_a_provider_that_returns_after_cancellation(context):
    store, provider = PracticeStore(), FakeProvider()
    session_id = store.create(context, key())["sessionId"]
    entered = asyncio.Event()
    async def late(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return "A stale message that must not be committed."
    provider.roleplay = late
    pending = asyncio.create_task(store.advance(session_id, key(), provider))
    await entered.wait()
    await store.stop(session_id)
    with pytest.raises(AppError, match="stopped"):
        await pending
    assert store.get(session_id).attempt.messages == []
    assert store.get(session_id).pending == "roleplay"


@pytest.mark.anyio
async def test_concurrent_generation_is_rejected_and_reset_removes_practice(context):
    store, provider = PracticeStore(), FakeProvider()
    session_id = store.create(context, key())["sessionId"]
    entered = asyncio.Event()
    async def waiting(*args):
        entered.set()
        await asyncio.Event().wait()
    provider.roleplay = waiting
    pending = asyncio.create_task(store.advance(session_id, key(), provider))
    await entered.wait()
    with pytest.raises(AppError, match="Wait"):
        await store.advance(session_id, key(), provider)
    await store.delete(session_id)
    with pytest.raises(asyncio.CancelledError):
        await pending
    with pytest.raises(AppError, match="expired"):
        store.get(session_id)


@pytest.mark.anyio
async def test_ten_simulated_cycles_preserve_context_and_keep_attempts_isolated(context):
    store, provider = PracticeStore(), FakeProvider()
    session_id = store.create(context, key())["sessionId"]
    original = copy.deepcopy(context.model_dump())
    for attempt in range(10):
        await store.advance(session_id, key(), provider)
        store.answer(session_id, ANSWER, key())
        store.finish(session_id, key())
        await store.advance(session_id, key(), provider)
        assert store.get(session_id).answers == 1
        assert store.get(session_id).context.model_dump() == original
        if attempt < 9:
            store.retry(session_id, key())
    assert len(provider.coach_calls) == 10
    with pytest.raises(AppError, match="ten attempts"):
        store.retry(session_id, key())


def test_expiry_and_snapshot_copies_do_not_leak_or_mutate_other_sessions(context):
    now = [0.0]
    store = PracticeStore(ttl_seconds=10, clock=lambda: now[0])
    first = store.create(context, key())
    second = store.create(context, key())
    first["attempts"][0]["messages"].append({"role": "user", "content": "Injected"})
    assert store.get(first["sessionId"]).attempt.messages == []
    assert store.get(second["sessionId"]).attempt.messages == []
    now[0] = 11
    with pytest.raises(AppError):
        store.get(first["sessionId"])
    assert store.sessions == {}


@pytest.mark.anyio
async def test_delete_expired_session_is_idempotent_and_cancels_inflight(context):
    now = [0.0]
    store, provider = PracticeStore(ttl_seconds=10, clock=lambda: now[0]), FakeProvider()
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def slow(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    provider.roleplay = slow
    session_id = store.create(context, key())["sessionId"]
    pending = asyncio.create_task(store.advance(session_id, key(), provider))
    await entered.wait()
    now[0] = 15
    await store.delete(session_id)
    assert cancelled.is_set()
    assert store.sessions == {}
    assert store.creations == {}
    with pytest.raises(asyncio.CancelledError):
        await pending


@pytest.mark.anyio
async def test_advance_refreshes_touched_and_stop_rejects_concurrent_delete(context):
    now = [0.0]
    store, provider = PracticeStore(ttl_seconds=10, clock=lambda: now[0]), FakeProvider()

    async def slow_reply(*args):
        now[0] = 8.0
        return "How does this affect Friday?"

    provider.roleplay = slow_reply
    session_id = store.create(context, key())["sessionId"]
    await store.advance(session_id, key(), provider)
    now[0] = 12.0
    assert store.get(session_id).attempt.messages[0]["content"] == "How does this affect Friday?"

    entered, release = asyncio.Event(), asyncio.Event()

    async def waiting(*args):
        entered.set()
        await release.wait()

    provider.roleplay = waiting
    store.answer(session_id, ANSWER, key())
    pending = asyncio.create_task(store.advance(session_id, key(), provider))
    await entered.wait()
    stop_task = asyncio.create_task(store.stop(session_id))
    await asyncio.sleep(0)
    await store.delete(session_id)
    with pytest.raises(AppError, match="expired"):
        await stop_task
    with pytest.raises((asyncio.CancelledError, AppError)):
        await pending
