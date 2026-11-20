import asyncio
import json

import httpx
import pytest

from server.config import Settings, parse_env
from server.errors import AppError
from server.models import validate_feedback
from server.providers import Providers
from server.speech import speech_segments
from conftest import QUESTION, ANSWER, feedback_value, wav_audio


def settings(**overrides):
    return Settings(gemini_key="private-gemini-value", groq_key="private-groq-value", retry_delay_seconds=0, **overrides)


def generated(value):
    return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(value)}]}]})


@pytest.mark.anyio
async def test_python_gemini_adapter_separates_modes_and_disables_request_storage(context):
    requests = []
    history = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": ANSWER}]
    def handler(request):
        body = json.loads(request.content)
        requests.append((request, body))
        return generated({"reply": QUESTION} if "simulated project manager" in body["system_instruction"] else feedback_value(history))
    provider = Providers(settings(), transport=httpx.MockTransport(handler))
    assert await provider.roleplay(context, []) == QUESTION
    assert (await provider.coach(context, history)).strength.quote
    assert requests[0][0].url.path.endswith("/interactions")
    assert requests[0][0].headers["x-goog-api-key"] == "private-gemini-value"
    assert requests[0][1]["model"] == "gemini-3.5-flash-lite"
    assert requests[0][1]["store"] is False
    assert requests[0][1]["response_format"]["mime_type"] == "application/json"
    assert "not a coding interview" in requests[0][1]["system_instruction"]
    assert "EXACT, contiguous excerpt" in requests[1][1]["system_instruction"]


@pytest.mark.parametrize("mutation", ["quote", "date", "number", "missing"])
def test_feedback_rejects_fabricated_evidence_and_commitments(context, mutation):
    history = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": ANSWER}]
    value = feedback_value(history)
    if mutation == "quote":
        value["strength"]["quote"] = QUESTION
    elif mutation == "date":
        value["improvedMessage"] += " We will finish on Monday."
    elif mutation == "number":
        value["improvedMessage"] += " This saves 50% of our effort."
    else:
        value["improvements"] = []
    with pytest.raises(AppError) as error:
        validate_feedback(value, history, context)
    assert error.value.code == "INVALID_PROVIDER_OUTPUT"


def test_honest_uncertainty_is_not_mistaken_for_the_month_may(context):
    history = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": ANSWER}]
    value = feedback_value(history)
    value["improvedMessage"] = "Search is ready for Friday. You may choose to add export after the release."
    assert validate_feedback(value, history, context)


def test_first_attempt_requires_an_empty_comparison(context):
    history = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": ANSWER}]
    value = feedback_value(history)
    value["comparison"] = "No previous attempt to compare."
    with pytest.raises(AppError) as error:
        validate_feedback(value, history, context)
    assert error.value.code == "INVALID_PROVIDER_OUTPUT"
    assert validate_feedback(value, history, context, previous_history=history)


@pytest.mark.parametrize("field", ["summary", "retryFocus", "suggestion", "missingFacts", "comparison"])
def test_unsupported_schedules_are_checked_across_actionable_feedback(context, field):
    history = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": ANSWER}]
    value = feedback_value(history)
    previous = None
    if field == "suggestion":
        value["improvements"][0]["suggestion"] = "Move PDF export to the next cycle."
    elif field == "missingFacts":
        value["missingFacts"] = ["Confirm delivery in the next cycle."]
    elif field == "comparison":
        value["comparison"] = "The next cycle is clearer than before."
        previous = history
    else:
        value[field] = "Move PDF export to the next cycle."
    with pytest.raises(AppError) as error:
        validate_feedback(value, history, context, previous)
    assert "next cycle" in error.value.validation_hint


@pytest.mark.parametrize("rewrite", [
    "Search is ready for Friday. PDF export will be ready in two working days.",
    "Search is ready for Friday. Plan PDF export for the next two working days.",
    "Search is ready for Friday. PDF export will finish two working days after Friday.",
])
def test_work_duration_cannot_become_delivery_timing(context, rewrite):
    history = [{"role": "user", "content": ANSWER}]
    value = feedback_value(history)
    value["improvedMessage"] = rewrite
    with pytest.raises(AppError) as error:
        validate_feedback(value, history, context)
    assert "delivery promise" in error.value.validation_hint


def test_unmeasured_impact_stays_unmeasured(context):
    history = [{"role": "user", "content": ANSWER}]
    value = feedback_value(history)
    value["improvedMessage"] = "Search is ready for Friday. There is no customer impact to consider."
    with pytest.raises(AppError) as error:
        validate_feedback(value, history, context)
    assert "unmeasured customer impact" in error.value.validation_hint
    value["improvedMessage"] = "Search is ready for Friday. No customer impact or time savings have been measured."
    assert validate_feedback(value, history, context)


@pytest.mark.anyio
async def test_transient_retry_is_bounded_and_preserves_the_original_payload(context):
    bodies = []
    def handler(request):
        bodies.append(request.content)
        return httpx.Response(503, json={"error": {}}) if len(bodies) == 1 else generated({"reply": QUESTION})
    provider = Providers(settings(), transport=httpx.MockTransport(handler))
    assert await provider.roleplay(context, []) == QUESTION
    assert len(bodies) == 2 and bodies[0] == bodies[1]


@pytest.mark.anyio
async def test_terms_error_is_specific_and_never_retried_or_leaked():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"error": {"code": "model_terms_required", "message": "private-groq-value upstream body"}})
    provider = Providers(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as error:
        await provider.speak("A short reply")
    assert error.value.code == "MODEL_TERMS_REQUIRED"
    assert "private-groq-value" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.anyio
async def test_second_groq_key_is_used_only_for_orpheus():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/speech"):
            return httpx.Response(200, content=wav_audio())
        return httpx.Response(200, json={"text": ANSWER})

    provider = Providers(settings(groq_voice_key="private-voice-value"), transport=httpx.MockTransport(handler))
    assert await provider.speak("A short reply")
    assert await provider.transcribe(wav_audio(), "audio/wav") == ANSWER
    assert requests[0].headers["authorization"] == "Bearer private-voice-value"
    assert requests[1].headers["authorization"] == "Bearer private-groq-value"


@pytest.mark.anyio
async def test_orpheus_retries_with_primary_key_when_voice_key_needs_terms():
    authorizations = []

    def handler(request):
        authorization = request.headers["authorization"]
        authorizations.append(authorization)
        if authorization == "Bearer private-voice-value":
            return httpx.Response(400, json={"error": {"code": "model_terms_required"}})
        return httpx.Response(200, content=wav_audio())

    provider = Providers(settings(groq_voice_key="private-voice-value"), transport=httpx.MockTransport(handler))
    assert await provider.speak("A short reply")
    assert authorizations == ["Bearer private-voice-value", "Bearer private-groq-value"]


@pytest.mark.anyio
async def test_voice_key_is_redacted_from_provider_diagnostics():
    reports = []
    provider = Providers(settings(groq_voice_key="private-voice-value"), diagnostic=reports.append,
        transport=httpx.MockTransport(lambda _request: httpx.Response(401, json={"error": {"message": "private-voice-value private-groq-value private-gemini-value"}})))
    with pytest.raises(AppError):
        await provider.speak("Hello")
    assert reports[0]["message"] == "[redacted] [redacted] [redacted]"
    assert "private-voice-value" not in repr(provider.settings)


@pytest.mark.anyio
async def test_redacted_diagnostics_do_not_expose_configured_keys(context):
    reports = []
    provider = Providers(settings(), diagnostic=reports.append, transport=httpx.MockTransport(lambda _request: httpx.Response(401, json={"error": {"message": "private-gemini-value private-groq-value"}})))
    with pytest.raises(AppError):
        await provider.roleplay(context, [])
    assert reports[0]["message"] == "[redacted] [redacted]"
    assert "private-" not in repr(settings())


@pytest.mark.anyio
async def test_timeout_and_task_cancellation_are_distinct(context):
    async def delayed(_request):
        await asyncio.sleep(10)
    provider = Providers(settings(timeout_seconds=0.01), transport=httpx.MockTransport(delayed))
    with pytest.raises(AppError) as error:
        await provider.roleplay(context, [])
    assert error.value.code == "PROVIDER_TIMEOUT"
    task = asyncio.create_task(provider.roleplay(context, []))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.anyio
async def test_whisper_multipart_and_blank_transcript_handling():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"text": " "})
    provider = Providers(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as error:
        await provider.transcribe(wav_audio(), "audio/wav")
    assert error.value.code == "EMPTY_TRANSCRIPT"
    assert 'multipart/form-data' in requests[0].headers["content-type"]
    assert b'filename="answer.wav"' in requests[0].content


@pytest.mark.anyio
async def test_invalid_audio_and_incomplete_gemini_response_are_rejected(context):
    provider = Providers(settings(), transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=b"not WAV")))
    with pytest.raises(AppError):
        await provider.speak("Hello")
    provider = Providers(settings(), transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"status": "incomplete", "steps": []})))
    with pytest.raises(AppError) as error:
        await provider.roleplay(context, [])
    assert error.value.code == "INVALID_PROVIDER_OUTPUT"


def test_speech_segmentation_preserves_order_and_codepoints():
    text = ("Search is ready for Friday. PDF export needs two additional working days. " * 20).strip()
    chunks = speech_segments(text)
    assert len(chunks) > 1
    assert " ".join(chunks) == text
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert all(len(chunk) <= 200 for chunk in speech_segments("🙂" * 420))
    assert speech_segments("**Clear** [message](https://example.com).") == ["Clear message."]
    assert speech_segments("We use C# for this service.") == ["We use C# for this service."]


def test_environment_parser_only_accepts_the_application_settings():
    assert parse_env('GROQ_API_KEY="value#123"\nPORT=4317 # comment\nUNRELATED_SECRET=ignore\nGEMINI_API_KEY=\n') == {"GROQ_API_KEY": "value#123", "PORT": "4317"}
