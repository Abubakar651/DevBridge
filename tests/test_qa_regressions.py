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
from server.prompts import COACH_PROMPT, ROLEPLAY_PROMPT
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


@pytest.mark.anyio
async def test_middleware_handles_broken_settings_loader_and_negative_content_length():
    def bad_loader():
        raise ValueError("PORT must be a valid port number.")

    broken_app = create_app(settings_loader=bad_loader)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=broken_app), base_url="http://127.0.0.1") as client:
        resp = await client.get("/api/config")
        assert resp.status_code == 500
        assert resp.json()["error"]["code"] == "CONFIGURATION_ERROR"

    ok_app = create_app(settings_loader=lambda: Settings(gemini_key="k", groq_key="g"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ok_app), base_url="http://127.0.0.1") as client:
        resp = await client.post("/api/practice", content=b"{}", headers={"content-type": "application/json", "content-length": "-5"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_INPUT"


@pytest.mark.anyio
async def test_api_returns_json_error_envelopes_for_http_and_unexpected_errors():
    class ExplodingStore(PracticeStore):
        def create(self, context, request_id):
            raise RuntimeError("sensitive internal detail")

    app = create_app(settings_loader=lambda: Settings(gemini_key="k", groq_key="g"), store=ExplodingStore())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://127.0.0.1") as client:
        missing = await client.get("/api/does-not-exist")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "NOT_FOUND"

        wrong_method = await client.post("/api/config")
        assert wrong_method.status_code == 405
        assert wrong_method.json()["error"]["code"] == "METHOD_NOT_ALLOWED"

        boom = await client.post("/api/practice", json={"context": DEFAULT_CONTEXT, "requestId": uid()})
        assert boom.status_code == 500
        assert boom.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "sensitive internal detail" not in boom.text


def test_validate_feedback_normalizes_curly_quotes_in_evidence_and_zero_impact(context):
    history = [{"role": "user", "content": 'We said "Search is ready", though we didn\'t test PDF export yet.'}]
    val = feedback_value(history)
    val["strength"]["quote"] = "we didn\u2019t test PDF export"
    val["improvements"][0]["quote"] = "\u201cSearch is ready\u201d"
    assert validate_feedback(val, history, context)

    curly_history = [{"role": "user", "content": "We haven\u2019t measured impact yet."}]
    val2 = feedback_value(curly_history)
    val2["strength"]["quote"] = "haven't measured impact"
    assert validate_feedback(val2, curly_history, context)

    for unmeasured_claim in (
        "Search is ready for Friday. There\u2019s no customer impact.",
        "Search is ready for Friday. There is no\ncustomer impact to consider.",
    ):
        bad = feedback_value(history)
        bad["improvedMessage"] = unmeasured_claim
        with pytest.raises(AppError) as error:
            validate_feedback(bad, history, context)
        assert "unmeasured customer impact" in error.value.validation_hint


@pytest.mark.parametrize(
    "ungrounded_date_claim",
    [
        "Search is ready for Friday. PDF export can ship during June.",
        "Search is ready for Friday. Wait until July for PDF export.",
        "Search is ready for Friday. Plan PDF export for May.",
        "Search is ready for Friday. We can deliver PDF export May 15.",
        "Search is ready for Friday. Expect PDF export June 15.",
        "Search is ready for Friday. Expect PDF export by 15 June.",
        "Search is ready for Friday. Targeting a June release.",
        "Search is ready for Friday. PDF export can ship next Friday.",
        "Search is ready for Friday. Target date 2026-06-15.",
    ],
)
def test_validate_feedback_rejects_date_and_month_regex_gaps(context, ungrounded_date_claim):
    history = [{"role": "user", "content": ANSWER}]
    val = feedback_value(history)
    val["summary"] = ungrounded_date_claim
    with pytest.raises(AppError) as error:
        validate_feedback(val, history, context)
    assert error.value.code == "INVALID_PROVIDER_OUTPUT"
    assert "new date" in error.value.validation_hint


def test_validate_feedback_date_modal_may_and_day_boundary_cases(context):
    history = [{"role": "user", "content": ANSWER}]
    for valid_modal in (
        "Search is ready for Friday. The timeline we agree on may shift after review.",
        "Search is ready for Friday. The release it goes in may change after approval.",
        "Search is ready for Friday. You may choose to add export after the release.",
    ):
        val = feedback_value(history)
        val["improvedMessage"] = valid_modal
        assert validate_feedback(val, history, context)

    may20_ctx = context.model_copy(update={"known_facts": "Search is ready for May 20. PDF export needs two additional working days."})
    collision = feedback_value(history)
    collision["improvedMessage"] = "Search is ready for May 2."
    with pytest.raises(AppError):
        validate_feedback(collision, history, may20_ctx)

    june15_ctx = context.model_copy(update={"known_facts": "Search is ready for June 15. PDF export needs two additional working days."})
    ordinal_ok = feedback_value(history)
    ordinal_ok["improvedMessage"] = "Search is ready for June 15th."
    assert validate_feedback(ordinal_ok, history, june15_ctx)

    modal_facts_ctx = context.model_copy(update={"known_facts": "Search is ready for Friday, and you may recommend next steps."})
    sneaky_may = feedback_value(history)
    sneaky_may["summary"] = "Plan PDF export in May."
    with pytest.raises(AppError):
        validate_feedback(sneaky_may, history, modal_facts_ctx)

    lowercase_until_may = feedback_value(history)
    lowercase_until_may["summary"] = "Wait until may."
    with pytest.raises(AppError):
        validate_feedback(lowercase_until_may, history, context)


def test_validate_feedback_handles_hyphenated_numbers_multipliers_and_percent(context):
    history = [{"role": "user", "content": ANSWER}]
    split_ctx = context.model_copy(update={"known_facts": "Search is ready for Friday. In 20 tests, 5 failed."})
    fabricated_25 = feedback_value(history)
    fabricated_25["improvedMessage"] = "Search is ready for Friday. Twenty-five tests failed."
    with pytest.raises(AppError):
        validate_feedback(fabricated_25, history, split_ctx)

    ctx_25 = context.model_copy(update={"known_facts": "Search is ready for Friday. In 25 reviewed tests, issues remain."})
    for grounded_25 in (
        "Search is ready for Friday. In twenty-five reviewed tests, issues remain.",
        "Search is ready for Friday. In twenty five reviewed tests, issues remain.",
    ):
        ok_25 = feedback_value(history)
        ok_25["improvedMessage"] = grounded_25
        assert validate_feedback(ok_25, history, ctx_25)

    for fabricated_mult in (
        "Search is ready for Friday. This affects two hundred users.",
        "Search is ready for Friday. This saves a hundred hours.",
    ):
        bad_mult = feedback_value(history)
        bad_mult["improvedMessage"] = fabricated_mult
        with pytest.raises(AppError):
            validate_feedback(bad_mult, history, context)

    ctx_100 = context.model_copy(update={"known_facts": "Search is ready for Friday. In 100 reviewed examples, 90% passed and 1,000 logs were checked."})
    ok_100 = feedback_value(history)
    ok_100["improvedMessage"] = "In one hundred reviewed examples, ninety percent passed and 1000 logs were checked."
    assert validate_feedback(ok_100, history, ctx_100)


def test_validate_feedback_delivery_timing_and_edge_cases(context):
    history = [{"role": "user", "content": ANSWER}]
    ctx_25 = context.model_copy(update={"known_facts": "Search is ready for Friday. PDF export needs 25 working days."})
    bad_timing_25 = feedback_value(history)
    bad_timing_25["improvedMessage"] = "Search is ready for Friday. PDF export will be ready in twenty-five working days."
    with pytest.raises(AppError) as error:
        validate_feedback(bad_timing_25, history, ctx_25)
    assert "delivery promise" in error.value.validation_hint

    ctx_2_3 = context.model_copy(update={"known_facts": "Search is ready for Friday. PDF export needs 2 to 3 working days."})
    for bad_phrase in (
        "Search is ready for Friday. PDF export will finish in 2 working days.",
        "Search is ready for Friday. PDF export will be ready in 2 more working days.",
        "Search is ready for Friday. PDF export will be ready in 2 to 3 working days.",
    ):
        bad = feedback_value(history)
        bad["improvedMessage"] = bad_phrase
        with pytest.raises(AppError) as error:
            validate_feedback(bad, history, ctx_2_3)
        assert "delivery promise" in error.value.validation_hint

    punct_quote = feedback_value(history)
    punct_quote["strength"]["quote"] = "."
    with pytest.raises(AppError):
        validate_feedback(punct_quote, history, context)

    empty_prev_comp = feedback_value(history)
    empty_prev_comp["comparison"] = "Improved clarity."
    with pytest.raises(AppError):
        validate_feedback(empty_prev_comp, history, context, previous_history=[])

    ws_comp = feedback_value(history)
    ws_comp["comparison"] = "   "
    validated = validate_feedback(ws_comp, history, context)
    assert validated.comparison == ""

    for bad_sched in (
        "Plan PDF export for an upcoming sprint.",
        "Plan PDF export for the next-sprint.",
    ):
        bad_s = feedback_value(history)
        bad_s["summary"] = bad_sched
        with pytest.raises(AppError):
            validate_feedback(bad_s, history, context)

    future_rel = feedback_value(history)
    future_rel["improvedMessage"] = "Search is ready for Friday. PDF export needs two additional working days and can be considered for a future release."
    assert validate_feedback(future_rel, history, context)


def test_prompts_prevent_attempt1_comparison_drift_and_grounding_leaks():
    assert "previousAttempt is null" in COACH_PROMPT
    assert '""' in COACH_PROMPT
    assert "No previous attempt to compare." in COACH_PROMPT
    assert "zero customer impact" in COACH_PROMPT.lower()
    assert "summary" in COACH_PROMPT and "retryFocus" in COACH_PROMPT and "suggestion" in COACH_PROMPT
    assert "EXACT, contiguous excerpt" in COACH_PROMPT
    assert "simulated project manager" in ROLEPLAY_PROMPT
    assert "not a coding interview" in ROLEPLAY_PROMPT
    assert "two days later" in ROLEPLAY_PROMPT
    assert "only one" in ROLEPLAY_PROMPT.lower() and "?" in ROLEPLAY_PROMPT
