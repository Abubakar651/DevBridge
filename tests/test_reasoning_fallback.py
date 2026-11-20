import asyncio
import json

import httpx
import pytest

from server.config import Settings
from server.errors import AppError
from server.models import RoleplayResponse, validate_feedback
from server.providers import Providers
from conftest import ANSWER, QUESTION, feedback_value


def configured(**overrides):
    return Settings(gemini_key="private-gemini", groq_key="private-groq", retry_delay_seconds=0, **overrides)


def completion(value, finish_reason="stop"):
    return httpx.Response(200, json={"choices": [{"finish_reason": finish_reason, "message": {"content": json.dumps(value)}}]})


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403, 404, 429, 502, 503, 504])
async def test_primary_errors_use_groq_with_the_same_scenario_and_transcript(context, status):
    calls = []
    history = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": ANSWER}]

    def handler(request):
        body = json.loads(request.content)
        calls.append((request, body))
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(status, json={"error": {"message": "private-gemini"}})
        return completion({"reply": QUESTION})

    provider = Providers(configured(), transport=httpx.MockTransport(handler))
    assert await provider.roleplay(context, history) == QUESTION
    primary, backup = calls[0][1], calls[-1][1]
    assert calls[-1][0].url.path == "/openai/v1/chat/completions"
    assert calls[-1][0].headers["authorization"] == "Bearer private-groq"
    assert backup["model"] == "openai/gpt-oss-20b"
    assert backup["messages"][0]["content"] == primary["system_instruction"]
    assert json.loads(backup["messages"][1]["content"]) == json.loads(primary["input"])
    assert backup["response_format"]["json_schema"]["schema"] == RoleplayResponse.model_json_schema()
    assert backup["response_format"]["json_schema"]["strict"] is True
    assert sum(call.url.host == "api.groq.com" for call, _ in calls) == 1
    assert provider.reasoning_events[-1]["provider"] == "groq"


@pytest.mark.anyio
async def test_primary_success_does_not_call_groq(context):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps({"reply": QUESTION})}]}]})

    provider = Providers(configured(), transport=httpx.MockTransport(handler))
    assert await provider.roleplay(context, []) == QUESTION
    assert len(calls) == 1
    assert provider.reasoning_events[-1]["provider"] == "gemini"


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["network", "timeout", "invalid_json", "invalid_schema"])
async def test_primary_transport_and_output_errors_also_fall_back(context, failure):
    async def handler(request):
        if request.url.host == "api.groq.com":
            return completion({"reply": QUESTION})
        if failure == "network":
            raise httpx.ConnectError("private-gemini", request=request)
        if failure == "timeout":
            await asyncio.Event().wait()
        text = "unreadable" if failure == "invalid_json" else '{"reply":""}'
        return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}]})

    provider = Providers(configured(timeout_seconds=0.02), transport=httpx.MockTransport(handler))
    assert await provider.roleplay(context, []) == QUESTION
    assert provider.reasoning_events[-1]["provider"] == "groq"


@pytest.mark.anyio
async def test_cancellation_does_not_start_a_backup_request(context):
    entered = asyncio.Event()
    calls = []

    async def handler(request):
        calls.append(request)
        entered.set()
        await asyncio.Event().wait()

    provider = Providers(configured(), transport=httpx.MockTransport(handler))
    task = asyncio.create_task(provider.roleplay(context, []))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(calls) == 1
    assert not provider.reasoning_events


@pytest.mark.anyio
async def test_missing_gemini_key_can_use_groq(context):
    calls = []

    def handler(request):
        calls.append(request)
        return completion({"reply": QUESTION})

    provider = Providers(Settings(groq_key="private-groq"), transport=httpx.MockTransport(handler))
    assert await provider.roleplay(context, []) == QUESTION
    assert len(calls) == 1 and calls[0].url.host == "api.groq.com"


@pytest.mark.anyio
async def test_without_a_backup_key_the_original_error_remains(context):
    provider = Providers(Settings(gemini_key="private-gemini"), transport=httpx.MockTransport(lambda _request: httpx.Response(401)))
    with pytest.raises(AppError) as error:
        await provider.roleplay(context, [])
    assert error.value.code == "PROVIDER_ACCESS"
    assert not provider.reasoning_events


@pytest.mark.anyio
@pytest.mark.parametrize("invalid", ["evidence", "date", "number", "schedule", "truncated"])
async def test_backup_coaching_is_subject_to_the_same_grounding_guards(context, invalid):
    history = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": ANSWER}]
    value = feedback_value(history)
    if invalid == "evidence":
        value["strength"]["quote"] = "Words the learner never said."
    elif invalid == "date":
        value["improvedMessage"] += " We guarantee delivery on Monday."
    elif invalid == "number":
        value["improvedMessage"] += " This saves 50% of our costs."
    elif invalid == "schedule":
        value["improvedMessage"] += " PDF export will ship next sprint."
    calls = []

    def handler(request):
        calls.append(request)
        return completion(value, "length" if invalid == "truncated" else "stop")

    provider = Providers(Settings(groq_key="private-groq"), transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as error:
        await provider.coach(context, history)
    assert error.value.code == "INVALID_PROVIDER_OUTPUT"
    assert len(calls) == 2


@pytest.mark.anyio
async def test_ungrounded_backup_output_can_be_repaired_once_without_changing_history(context):
    history = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": ANSWER}]
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        value = feedback_value(history)
        if len(calls) == 1:
            value["improvedMessage"] += " PDF export ships next sprint."
        return completion(value)

    provider = Providers(Settings(groq_key="private-groq"), transport=httpx.MockTransport(handler))
    notes = await provider.coach(context, history)
    assert notes.improved_message == feedback_value(history)["improvedMessage"]
    assert len(calls) == 2
    assert calls[0]["messages"][1] == calls[1]["messages"][1]
    assert "SERVER VALIDATION" in calls[1]["messages"][0]["content"]
    assert any(event["event"] == "reasoning_validation_retry" for event in provider.reasoning_events)


@pytest.mark.anyio
async def test_backup_rejects_a_stakeholder_reply_that_answers_for_the_learner(context):
    provider = Providers(Settings(groq_key="private-groq"), transport=httpx.MockTransport(lambda _request: completion({"reply": "Search is ready for Friday. We will release it now."})))
    with pytest.raises(AppError) as error:
        await provider.roleplay(context, [])
    assert error.value.code == "INVALID_PROVIDER_OUTPUT"


@pytest.mark.parametrize("schedule", ["next cycle", "next iteration", "next release"])
def test_rewrites_cannot_add_other_unsupplied_release_schedules(context, schedule):
    history = [{"role": "user", "content": ANSWER}]
    value = feedback_value(history)
    value["improvedMessage"] += " PDF export will ship in the " + schedule + "."
    with pytest.raises(AppError) as error:
        validate_feedback(value, history, context)
    assert schedule in error.value.validation_hint
    assert "retain only the work duration" in error.value.validation_hint


def test_a_relative_schedule_explicitly_present_in_known_facts_is_allowed(context):
    history = [{"role": "user", "content": ANSWER}]
    context.known_facts += " If approved, PDF export can be scheduled in the next cycle."
    value = feedback_value(history)
    value["improvedMessage"] += " If approved, PDF export can be scheduled in the next cycle."
    assert validate_feedback(value, history, context)


@pytest.mark.anyio
async def test_bad_backup_access_surfaces_without_a_fallback_loop_or_key_leak(context):
    diagnostics = []
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, json={"error": {"message": "private-gemini private-groq"}})

    provider = Providers(configured(), diagnostic=diagnostics.append, transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as error:
        await provider.roleplay(context, [])
    assert len(calls) == 2
    assert error.value.code == "PROVIDER_ACCESS"
    assert "private-" not in str(error.value)
    assert "private-" not in json.dumps(diagnostics)


@pytest.mark.anyio
async def test_primary_can_recover_on_the_next_turn(context):
    primary_calls = 0

    def handler(request):
        nonlocal primary_calls
        if request.url.host == "api.groq.com":
            return completion({"reply": QUESTION})
        primary_calls += 1
        if primary_calls == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps({"reply": QUESTION})}]}]})

    provider = Providers(configured(), transport=httpx.MockTransport(handler))
    assert await provider.roleplay(context, []) == QUESTION
    assert await provider.roleplay(context, []) == QUESTION
    successes = [event["provider"] for event in provider.reasoning_events if event["event"] == "reasoning_success"]
    assert successes == ["groq", "gemini"]


@pytest.mark.anyio
async def test_groq_rate_limit_falls_back_to_openrouter_with_same_validators(context):
    calls = []
    history = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": ANSWER}]

    def handler(request):
        body = json.loads(request.content)
        calls.append((request, body))
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(429, json={"error": {"message": "gemini quota"}})
        if request.url.host == "api.groq.com":
            return httpx.Response(429, json={"error": {"message": "groq 8000 tpm"}})
        return completion(feedback_value(history))

    provider = Providers(configured(openrouter_key="private-openrouter"), transport=httpx.MockTransport(handler))
    expected = feedback_value(history)
    notes = await provider.coach(context, history)
    assert notes.strength.quote == expected["strength"]["quote"]
    assert calls[-1][0].url.host == "openrouter.ai"
    assert calls[-1][0].url.path == "/api/v1/chat/completions"
    assert calls[-1][0].headers["authorization"] == "Bearer private-openrouter"
    assert calls[-1][1]["model"] == "openai/gpt-oss-20b"
    assert calls[-1][1]["provider"] == {"require_parameters": True}
    assert calls[-1][1]["response_format"]["json_schema"]["strict"] is True
    assert provider.reasoning_events[-1]["provider"] == "openrouter"


@pytest.mark.anyio
async def test_openrouter_only_supports_single_validation_retry(context):
    history = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": ANSWER}]
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        value = feedback_value(history)
        if len(calls) == 1:
            value["improvedMessage"] += " PDF export ships next sprint."
        return completion(value)

    provider = Providers(Settings(openrouter_key="private-openrouter", retry_delay_seconds=0), transport=httpx.MockTransport(handler))
    notes = await provider.coach(context, history)
    assert notes.improved_message == feedback_value(history)["improvedMessage"]
    assert len(calls) == 2
    assert "SERVER VALIDATION" in calls[1]["messages"][0]["content"]
    assert provider.reasoning_events[-1]["provider"] == "openrouter"


@pytest.mark.anyio
async def test_cancellation_during_groq_does_not_fall_back_to_openrouter(context):
    entered = asyncio.Event()
    calls = []

    async def handler(request):
        calls.append(request.url.host)
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(429)
        entered.set()
        await asyncio.Event().wait()

    provider = Providers(configured(openrouter_key="private-openrouter"), transport=httpx.MockTransport(handler))
    task = asyncio.create_task(provider.roleplay(context, []))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "openrouter.ai" not in calls
