"""Focused QA gap-coverage and bug-reproduction tests (no live provider calls)."""

import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from conftest import ANSWER, FakeProvider, QUESTION, feedback_value, wav_audio
from server.app import create_app
from server.config import PROJECT_ROOT, Settings, load_settings, parse_env
from server.errors import AppError
from server.models import Context, validate_feedback
from server.providers import Providers
from server.scenario import DEFAULT_CONTEXT
from server.sessions import PracticeStore
from server.speech import speech_segments


def uid() -> str:
    return str(uuid.uuid4())


def test_env_precedence_root_project_and_environment(tmp_path):
    root = tmp_path / "repo"
    project = root / "Internships" / "NETSOL" / "Voice_Coach"
    server_dir = project / "server"
    server_dir.mkdir(parents=True)
    (root / ".env").write_text("GEMINI_API_KEY=root-gem\nGROQ_API_KEY=root-groq\nGROQ_API_KEY_2=root-voice\nPORT=4318\n", encoding="utf-8")
    (project / ".env").write_text("GEMINI_API_KEY=\nGROQ_API_KEY=proj-groq\nGROQ_API_KEY2=proj-voice\n", encoding="utf-8")

    with patch("server.config.PROJECT_ROOT", project):
        # Empty GEMINI_API_KEY in project .env preserves root .env; project overrides GROQ_API_KEY
        s1 = load_settings({})
        assert s1.gemini_key == "root-gem"
        assert s1.groq_key == "proj-groq"
        assert s1.groq_voice_key == "proj-voice"
        assert s1.port == 4318

        # Explicit environment overrides both .env files
        s2 = load_settings({"GEMINI_API_KEY": "env-gem", "GROQ_API_KEY2": "env-voice", "PORT": "4399"})
        assert s2.gemini_key == "env-gem"
        assert s2.groq_key == "proj-groq"
        assert s2.groq_voice_key == "env-voice"
        assert s2.port == 4399

        # The legacy underscore spelling remains usable when the preferred name is absent.
        (project / ".env").write_text("GROQ_API_KEY=proj-groq\n", encoding="utf-8")
        s3 = load_settings({})
        assert s3.groq_voice_key == "root-voice"


@pytest.mark.anyio
async def test_gemini_coach_failure_falls_back_to_groq_with_previous_attempt(context):
    history = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": ANSWER}]
    previous = [{"role": "assistant", "content": QUESTION}, {"role": "user", "content": "Old answer."}]
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append((request.url.host, body))
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(429, json={"error": {"message": "Quota exceeded"}})
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(feedback_value(history, previous))}}]},
        )

    provider = Providers(Settings(gemini_key="g-key", groq_key="q-key", retry_delay_seconds=0), transport=httpx.MockTransport(handler))
    result = await provider.coach(context, history, previous)
    assert result.comparison
    assert [host for host, _ in seen] == ["generativelanguage.googleapis.com", "api.groq.com"]
    gemini_payload = json.loads(seen[0][1]["input"])
    groq_payload = json.loads(seen[1][1]["messages"][1]["content"])
    assert gemini_payload == groq_payload
    assert groq_payload["previousAttempt"] == previous


@pytest.mark.anyio
async def test_exhausted_backup_coach_retries_keeps_accepted_answer_and_feedback_uncommitted(context):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(503, json={"error": {"message": "unavailable"}})
        bad = feedback_value([{"role": "user", "content": ANSWER}])
        bad["strength"]["quote"] = "Never spoken by learner"
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(bad)}}]})

    settings = Settings(gemini_key="g-key", groq_key="q-key", retry_delay_seconds=0)
    store = PracticeStore()
    app = create_app(settings_loader=lambda: settings, provider_factory=lambda s: Providers(s, transport=httpx.MockTransport(handler)), store=store)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        sid = (await client.post("/api/practice", json={"context": DEFAULT_CONTEXT, "requestId": uid()})).json()["sessionId"]
        # Seed opening + learner answer directly via store to isolate coaching failure test
        practice = store.get(sid)
        practice.attempt.messages.append({"role": "assistant", "content": QUESTION})
        practice.pending = None
        await client.post(f"/api/practice/{sid}/answer", json={"requestId": uid(), "text": ANSWER})
        await client.post(f"/api/practice/{sid}/finish", json={"requestId": uid()})
        calls = 0
        resp = await client.post(f"/api/practice/{sid}/advance", json={"requestId": uid()})
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "INVALID_PROVIDER_OUTPUT"
        # Gemini attempted 2x (503 transient retry), Groq attempted 2x (initial + 1 corrective retry)
        assert calls == 4
        assert practice.answers == 1
        assert practice.attempt.feedback is None
        assert practice.pending == "coach"


@pytest.mark.anyio
async def test_orpheus_falls_back_to_primary_groq_key_when_key2_absent():
    auths = []

    def handler(request):
        auths.append((request.url.path, request.headers.get("authorization")))
        if request.url.path.endswith("/speech"):
            return httpx.Response(200, content=wav_audio())
        return httpx.Response(200, json={"text": ANSWER})

    provider = Providers(Settings(groq_key="primary-key", groq_voice_key=""), transport=httpx.MockTransport(handler))
    await provider.speak("Hello")
    await provider.transcribe(wav_audio(), "audio/wav")
    assert auths == [
        ("/openai/v1/audio/speech", "Bearer primary-key"),
        ("/openai/v1/audio/transcriptions", "Bearer primary-key"),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "content_type",
    ["audio/webm", "audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"],
)
async def test_all_supported_audio_mime_types_and_parameters_accepted(content_type):
    provider = FakeProvider()
    app = create_app(settings_loader=lambda: Settings(groq_key="k"), provider_factory=lambda _s: provider)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        resp = await client.post("/api/transcribe", content=wav_audio(), headers={"content-type": content_type})
        assert resp.status_code == 200
        assert resp.json()["text"] == ANSWER


@pytest.mark.anyio
async def test_host_origin_and_sec_fetch_site_edge_cases():
    app = create_app(settings_loader=lambda: Settings(groq_key="k"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        assert (await client.get("/api/config", headers={"host": "[::1]:4317", "origin": "http://[::1]:4317"})).status_code == 200
        assert (await client.get("/api/config", headers={"host": "127.0.0.1:4317", "origin": "http://localhost:4317"})).status_code == 403
        assert (await client.get("/api/config", headers={"host": "127.0.0.1:4317", "origin": "null"})).status_code == 403
        assert (await client.get("/api/config", headers={"host": "127.0.0.1:4317", "sec-fetch-site": "cross-site"})).status_code == 403
        assert (await client.get("/api/config", headers={"host": "user@127.0.0.1:4317"})).status_code == 403
        assert (await client.get("/api/config", headers={"host": "[invalid"})).status_code == 400
        assert (await client.get("/api/config", headers={"host": "127.0.0.1:4317", "content-length": "abc"})).status_code == 400
        for private_path in ("/.env", "/server/app.py", "/server/providers.py", "/docs/ANTIGRAVITY_QA_PROMPT.md", "/../.env"):
            assert (await client.get(private_path)).status_code == 404


@pytest.mark.anyio
async def test_session_isolation_max_sessions_and_expiry_frees_slot(context):
    now = [0.0]
    store = PracticeStore(ttl_seconds=10, max_sessions=2, clock=lambda: now[0])
    provider = FakeProvider()
    req_a = uid()
    s_a = store.create(context, req_a)["sessionId"]
    s_b = store.create(context, uid())["sessionId"]

    with pytest.raises(AppError) as limit_err:
        store.create(context, uid())
    assert limit_err.value.code == "SESSION_LIMIT"

    await store.advance(s_a, uid(), provider)
    assert store.get(s_b).attempt.messages == []

    now[0] = 11.0
    s_c = store.create(context, req_a)["sessionId"]
    assert s_c != s_a


@pytest.mark.anyio
async def test_duplicate_and_conflicting_request_ids_and_unbroken_speech_segment(context):
    store = PracticeStore()
    provider = FakeProvider()
    req_create = uid()
    sid = store.create(context, req_create)["sessionId"]
    other_ctx = context.model_copy(update={"discipline": "AI/ML engineer"})
    with pytest.raises(AppError) as conflict:
        store.create(other_ctx, req_create)
    assert conflict.value.code == "REQUEST_CONFLICT"

    await store.advance(sid, uid(), provider)
    ans_id = uid()
    store.answer(sid, ANSWER, ans_id)
    with pytest.raises(AppError) as conflict2:
        store.finish(sid, ans_id)
    assert conflict2.value.code == "REQUEST_CONFLICT"

    fin_id = uid()
    snap1 = store.finish(sid, fin_id)
    snap2 = store.finish(sid, fin_id)
    assert snap1["pendingStage"] == snap2["pendingStage"] == "coach"
    assert [len(c) for c in speech_segments("a" * 450, limit=200)] == [200, 200, 50]


@pytest.mark.anyio
async def test_chunked_oversize_json_body_returns_413_error_envelope():
    app = create_app(settings_loader=lambda: Settings(groq_key="k"))

    async def large_json():
        for _ in range(10):
            yield b"x" * 10000

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        resp = await client.post("/api/practice", content=large_json(), headers={"content-type": "application/json"})
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_parse_env_handles_quotes_inside_inline_comments():
    parsed = parse_env('GROQ_API_KEY="abc" # note "quoted"\n')
    assert parsed["GROQ_API_KEY"] == "abc"


def test_parse_env_trims_quoted_values_and_ignores_blank_quotes():
    parsed = parse_env('HOST=" 127.0.0.1 "\nGEMINI_MODEL=\' gemini-3.5-flash-lite \'\nGROQ_API_KEY="   "\n')
    assert parsed == {"HOST": "127.0.0.1", "GEMINI_MODEL": "gemini-3.5-flash-lite"}


def test_load_settings_checks_workspace_parent_and_shallow_paths(tmp_path):
    workspace = tmp_path / "Internships"
    project = workspace / "NETSOL" / "Voice_Coach"
    project.mkdir(parents=True)
    (workspace / ".env").write_text("GEMINI_API_KEY=ws-gem\nHOST=localhost\n", encoding="utf-8")

    with patch("server.config.PROJECT_ROOT", project):
        s1 = load_settings({})
        assert s1.gemini_key == "ws-gem"
        assert s1.host == "localhost"

        # Whitespace-only environment override must not clobber a valid .env key
        s2 = load_settings({"GEMINI_API_KEY": "   "})
        assert s2.gemini_key == "ws-gem"

    with patch("server.config.PROJECT_ROOT", Path("/app")):
        s3 = load_settings({})
        assert s3.port == 4317


def test_load_settings_rejects_non_numeric_port_with_clear_error():
    with pytest.raises(ValueError, match=r"^PORT must be a valid port number\.$"):
        load_settings({"PORT": "abc"})


def test_validate_feedback_rejects_number_words_absent_from_facts(context):
    history = [{"role": "user", "content": ANSWER}]
    val = feedback_value(history)
    val["improvedMessage"] = "Search is ready for Friday. PDF export needs three additional working days."
    with pytest.raises(AppError):
        validate_feedback(val, history, context)


def test_validate_feedback_allows_literal_this_release_when_friday_release_in_facts(context):
    history = [{"role": "user", "content": ANSWER}]
    val = feedback_value(history)
    val["improvedMessage"] = "Search is ready for this release. PDF export needs two additional working days."
    assert validate_feedback(val, history, context)


def test_validate_feedback_rejects_duration_turned_into_delivery_timing(context):
    history = [{"role": "user", "content": ANSWER}]
    val = feedback_value(history)
    val["improvedMessage"] = "Search is ready for Friday. PDF export will be ready for the next two working days after Friday."
    with pytest.raises(AppError):
        validate_feedback(val, history, context)


def test_browser_reset_uses_one_server_cleanup_request():
    source = (PROJECT_ROOT / "web" / "session.js").read_text(encoding="utf-8")
    reset_source = source[source.index("  reset() {"):]
    assert "this.api.reset(id)" in reset_source
    assert "this.stop()" not in reset_source
    assert "this.api.stop" not in reset_source


def test_validate_feedback_allows_grounded_release_after_approval_phrasing(context):
    history = [{"role": "user", "content": ANSWER}]
    for sentence in (
        "Search is ready for Friday. PDF export needs two additional working days and can be released after scope approval.",
        "Search can be released in this release, while PDF export needs two additional working days.",
    ):
        val = feedback_value(history)
        val["improvedMessage"] = sentence
        assert validate_feedback(val, history, context)
