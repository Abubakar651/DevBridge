"""Focused QA gap-coverage and bug-reproduction tests (no live provider calls)."""

import asyncio
import json
import shutil
import subprocess
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
    assert "simulated workplace stakeholder" in ROLEPLAY_PROMPT
    assert "not a coding interview" in ROLEPLAY_PROMPT
    assert "two days later" in ROLEPLAY_PROMPT
    assert "only one" in ROLEPLAY_PROMPT.lower() and "?" in ROLEPLAY_PROMPT


def test_speech_segments_boundary_and_markdown_edge_cases():
    # Word boundary exactly at limit (space at index limit) must not split early.
    exact_word_fit = "Hello " + ("b" * 194) + " next."
    assert speech_segments(exact_word_fit, limit=200) == ["Hello " + ("b" * 194), "next."]

    # Sentence boundary ending at limit - 1 ('.' at index 199, ' ' at index 200).
    exact_sentence_fit = "Hello world. " + ("a" * 186) + ". Next sentence."
    assert speech_segments(exact_sentence_fit, limit=200) == ["Hello world. " + ("a" * 186) + ".", "Next sentence."]

    # Snake_case identifiers stay intact while Markdown emphasis, blockquotes, strike, and parens-in-URL are stripped.
    assert speech_segments("> Check _known_facts_ and ~~old~~ [spec](https://example.com/v1_(draft)).") == [
        "Check known_facts and old spec."
    ]
    assert speech_segments("* First item\n+ Second item") == ["First item Second item"]

    with pytest.raises(ValueError):
        speech_segments("Hello", limit=True)


def run_node_module(script: str):
    node = shutil.which("node")
    assert node, "Node.js is required to execute browser module regression tests."
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Node script failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


def test_web_api_encodes_session_ids_normalizes_errors_and_validates_payloads():
    run_node_module(
        """
        import assert from 'node:assert/strict';
        import { api, request } from './web/api.js';

        const calls = [];
        globalThis.fetch = async (url, options) => {
          calls.push([url, options]);
          if (url === '/api/fail-http') {
            return { ok: false, status: 503, json: async () => ({ error: { code: 'PROVIDER_BUSY', message: 'Busy' } }) };
          }
          if (url === '/api/bad-json') {
            return { ok: true, status: 200, json: async () => { throw new SyntaxError('Unexpected token <'); } };
          }
          if (url === '/api/speech/segments') {
            return { ok: true, status: 200, json: async () => ({ wrongKey: true }) };
          }
          if (url === '/api/speak') {
            return { ok: true, status: 200, blob: async () => ({ size: 44 }) };
          }
          return { ok: true, status: 204, json: async () => ({}) };
        };

        await assert.rejects(() => api.stop(''), err => err.code === 'INVALID_INPUT');
        await assert.rejects(() => api.reset(undefined), err => err.code === 'INVALID_INPUT');
        await assert.rejects(() => api.answer('', 'hi', 'req-1234567890123456'), err => err.code === 'INVALID_INPUT');
        assert.equal(calls.length, 0);

        await api.stop('abc/def?x=1');
        assert.equal(calls.at(-1)[0], '/api/practice/abc%2Fdef%3Fx%3D1/stop');
        assert.equal(calls.at(-1)[1].keepalive, true);

        await assert.rejects(() => request('fail-http'), err => err.status === 503 && err.code === 'PROVIDER_BUSY');
        await assert.rejects(() => request('bad-json'), err => err.code === 'INVALID_RESPONSE');
        await assert.rejects(() => api.segments('hello'), err => err.code === 'INVALID_RESPONSE');

        await api.transcribe({ type: '   ' });
        assert.equal(calls.at(-1)[1].headers['Content-Type'], 'audio/webm');

        const blob = await api.speak('hi');
        assert.equal(blob.size, 44);

        const controller = new AbortController();
        await api.config(controller.signal);
        assert.equal(calls.at(-1)[1].signal, controller.signal);

        globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
        await assert.rejects(() => api.config(), err => err.code === 'NETWORK_ERROR' && /local server/i.test(err.message));

        globalThis.fetch = async () => { throw new DOMException('Cancelled', 'AbortError'); };
        await assert.rejects(() => api.config(), err => err.name === 'AbortError');
        """
    )


def test_web_audio_recorder_mime_fallback_invalid_state_and_cleanup():
    run_node_module(
        """
        import assert from 'node:assert/strict';
        import { Recorder, SpeechPlayer } from './web/audio.js';

        const makeStream = () => {
          let stopped = 0;
          return {
            get stopped() { return stopped; },
            getTracks() { return [{ stop() { stopped++; } }]; },
          };
        };

        // 1. Missing isTypeSupported should not throw, and missing presets should fall back cleanly.
        {
          const stream = makeStream();
          const calls = [];
          class NoSupportMethodRecorder {
            constructor(s, opts) { calls.push(opts); this.state = 'inactive'; this.mimeType = ''; }
            start() { this.state = 'recording'; }
            stop() { this.state = 'inactive'; this.onstop?.(); }
          }
          const rec = new Recorder({ mediaDevices: { getUserMedia: async () => stream }, RecorderClass: NoSupportMethodRecorder });
          await rec.start(() => {});
          assert.equal(calls[0], undefined);
          const blob = await rec.finish();
          assert.equal(blob.type, 'audio/webm');
          assert.equal(stream.stopped, 1);
          assert.equal(rec.recorder, null);
        }

        // 2. Backend-supported MIME outside original 4 presets (e.g. audio/ogg) and fallback if { mimeType } throws.
        {
          const stream = makeStream();
          const ctorArgs = [];
          class OggFallbackRecorder {
            static isTypeSupported(t) { return t === 'audio/ogg'; }
            constructor(s, opts) {
              ctorArgs.push(opts);
              if (opts) throw new DOMException('Unsupported', 'NotSupportedError');
              this.state = 'inactive'; this.mimeType = '';
            }
            start() { this.state = 'recording'; }
            stop() {
              this.state = 'inactive';
              this.ondataavailable?.({ data: new Blob(['abc'], { type: 'audio/ogg' }) });
              this.onstop?.();
            }
          }
          const rec = new Recorder({ mediaDevices: { getUserMedia: async () => stream }, RecorderClass: OggFallbackRecorder });
          await rec.start(() => {});
          assert.deepEqual(ctorArgs, [{ mimeType: 'audio/ogg' }, undefined]);
          const blob = await rec.finish();
          assert.equal(blob.type, 'audio/ogg');
          assert.equal(stream.stopped, 1);
        }

        // 3. Pre-aborted signal in finish() + InvalidStateError in finish() and cancel() must release mic tracks.
        {
          const stream1 = makeStream();
          class PreAbortedRecorder {
            static isTypeSupported() { return false; }
            constructor() { this.state = 'inactive'; }
            start() { this.state = 'recording'; }
            stop() { throw new Error('stop should not run on pre-aborted signal'); }
          }
          const rec1 = new Recorder({ mediaDevices: { getUserMedia: async () => stream1 }, RecorderClass: PreAbortedRecorder });
          await rec1.start(() => {});
          const ac = new AbortController(); ac.abort();
          await assert.rejects(() => rec1.finish(ac.signal), err => err.name === 'AbortError');
          assert.equal(stream1.stopped, 1);
          assert.equal(rec1.recorder, null);

          const stream2 = makeStream();
          class ThrowingStopRecorder {
            static isTypeSupported() { return false; }
            constructor() { this.state = 'recording'; }
            start() { this.state = 'recording'; }
            stop() { throw new DOMException('Invalid state', 'InvalidStateError'); }
          }
          const rec2 = new Recorder({ mediaDevices: { getUserMedia: async () => stream2 }, RecorderClass: ThrowingStopRecorder });
          await rec2.start(() => {});
          await assert.rejects(() => rec2.finish(), /recording could not be completed/i);
          assert.equal(stream2.stopped, 1);
          assert.equal(rec2.recorder, null);

          const stream3 = makeStream();
          class PausedThrowingStopRecorder {
            static isTypeSupported() { return false; }
            constructor() { this.state = 'inactive'; this.stops = 0; }
            start() { this.state = 'paused'; }
            stop() {
              this.stops++;
              if (this.stops > 1) throw new DOMException('Invalid state', 'InvalidStateError');
            }
          }
          const rec3 = new Recorder({ mediaDevices: { getUserMedia: async () => stream3 }, RecorderClass: PausedThrowingStopRecorder });
          await rec3.start(() => {});
          const pending = rec3.finish();
          rec3.cancel();
          await assert.rejects(() => pending, err => err.name === 'AbortError');
          assert.equal(stream3.stopped, 1);
          assert.equal(rec3.recorder, null);
        }

        // 4. SpeechPlayer: pre-aborted check, empty segments skips guardMs, sync audio.play() throw revokes URL.
        {
          let segmented = 0;
          let revoked = 0;
          const player = new SpeechPlayer(async () => new Blob(['RIFF']), {
            segmentText: async () => { segmented++; return []; },
            createAudio: () => ({
              play() { throw new Error('Sync failure'); },
              pause() {},
            }),
            createUrl: () => 'blob:fake',
            revokeUrl: () => { revoked++; },
            guardMs: 5000,
          });
          const ac = new AbortController(); ac.abort();
          await assert.rejects(() => player.play('hi', { signal: ac.signal }), err => err.name === 'AbortError');
          assert.equal(segmented, 0);

          const start = Date.now();
          await player.play('** **');
          assert.ok(Date.now() - start < 500);

          const player2 = new SpeechPlayer(async () => new Blob(['RIFF']), {
            segmentText: async () => ['hello'],
            createAudio: () => ({
              play() { throw new Error('Sync failure'); },
              pause() {},
            }),
            createUrl: () => 'blob:fake-2',
            revokeUrl: () => { revoked++; },
            guardMs: 0,
          });
          await assert.rejects(() => player2.play('hello'), /Audio playback failed/i);
          assert.equal(revoked, 1);
        }
        """
    )


def test_web_session_preserves_start_with_answer_draft_and_avoids_stop_on_mute():
    run_node_module(
        """
        import assert from 'node:assert/strict';
        import { PracticeSession } from './web/session.js';

        const noopRecorder = { supported: true, cancel() {}, start: async () => {}, finish: async () => new Blob(['a']) };
        const noopPlayer = { stop() {}, play: async () => {} };

        // 1. startWithAnswer() keeps queuedAnswer when create succeeds and opening advance fails, then submits on recover().
        {
          const calls = [];
          let advanceCalls = 0;
          const api = {
            create: async (context) => {
              calls.push('create');
              return { sessionId: 's1', context, maxAnswers: 3, pendingStage: 'roleplay', attempts: [{ number: 1, messages: [], feedback: null }], playback: null };
            },
            advance: async (id) => {
              calls.push('advance');
              advanceCalls++;
              if (advanceCalls === 1) { const err = new Error('Busy'); err.code = 'PROVIDER_BUSY'; throw err; }
              if (advanceCalls === 2) {
                return { sessionId: id, maxAnswers: 3, pendingStage: null, attempts: [{ number: 1, messages: [{ role: 'assistant', content: 'Update?' }], feedback: null }], playback: null };
              }
              return { sessionId: id, maxAnswers: 3, pendingStage: null, attempts: [{ number: 1, messages: [{ role: 'assistant', content: 'Update?' }, { role: 'user', content: 'My draft' }, { role: 'assistant', content: 'Next?' }], feedback: null }], playback: null };
            },
            answer: async (id, text) => {
              calls.push(['answer', text]);
              return { sessionId: id, maxAnswers: 3, pendingStage: 'roleplay', attempts: [{ number: 1, messages: [{ role: 'assistant', content: 'Update?' }, { role: 'user', content: text }], feedback: null }], playback: null };
            },
            stop: async () => ({}), reset: async () => ({}),
          };
          const session = new PracticeSession({ api, recorder: noopRecorder, player: noopPlayer });
          await session.startWithAnswer({ scenarioId: 'release-update' }, 'My draft');
          assert.equal(session.state, 'ERROR');
          assert.equal(session.queuedAnswer, 'My draft');
          await session.recover();
          assert.equal(session.state, 'IDLE');
          assert.deepEqual(calls, ['create', 'advance', 'advance', ['answer', 'My draft'], 'advance']);
          assert.equal(session.answers, 1);
        }

        // 2. setVoiceEnabled(false) during active speech cancels playback locally WITHOUT calling api.stop().
        {
          let stopCalls = 0;
          let playerStopped = 0;
          let releasePlay;
          const api = {
            create: async () => ({ sessionId: 's2', maxAnswers: 3, pendingStage: 'roleplay', attempts: [{ number: 1, messages: [], feedback: null }], playback: null }),
            advance: async () => ({ sessionId: 's2', maxAnswers: 3, pendingStage: null, attempts: [{ number: 1, messages: [{ role: 'assistant', content: 'Q?' }], feedback: null }], playback: { text: 'Q?', speaker: 'Project manager' } }),
            stop: async () => { stopCalls++; return {}; },
            reset: async () => ({}),
          };
          const player = {
            stop() { playerStopped++; releasePlay?.(new DOMException('Cancelled', 'AbortError')); },
            play: (_text, { onState }) => new Promise((_res, rej) => { releasePlay = rej; onState('SPEAKING'); }),
          };
          const session = new PracticeSession({ api, recorder: noopRecorder, player });
          const running = session.start({ scenarioId: 'release-update' });
          await new Promise(r => setTimeout(r, 10));
          assert.equal(session.pending?.type, 'speak');
          await session.setVoiceEnabled(false);
          await running;
          assert.equal(stopCalls, 0);
          assert.ok(playerStopped >= 1);
          assert.equal(session.pending, null);
          assert.equal(session.state, 'IDLE');
        }

        // 3. Double runPending() while awaiting this.stopping is blocked via busy state; same-gen AbortError resets to IDLE.
        {
          let resolveStop;
          let createCalls = 0;
          const api = {
            create: async () => { createCalls++; return { sessionId: 's3', maxAnswers: 3, pendingStage: null, attempts: [{ number: 1, messages: [], feedback: null }], playback: null }; },
            advance: async () => { throw new DOMException('Aborted', 'AbortError'); },
            stop: async () => new Promise(r => { resolveStop = () => r({}); }),
            reset: async () => ({}),
          };
          const session = new PracticeSession({ api, recorder: noopRecorder, player: noopPlayer });
          session.snapshot = { sessionId: 'old', maxAnswers: 3, attempts: [{ number: 1, messages: [] }] };
          session.stop();
          session.snapshot = null;
          const p1 = session.start({ scenarioId: 'release-update' });
          assert.equal(session.busy, true);
          const p2 = session.start({ scenarioId: 'release-update' });
          resolveStop();
          await Promise.all([p1, p2]);
          assert.equal(createCalls, 1);

          // Same-generation AbortError in runPending / finishRecording must not strand state in THINKING/TRANSCRIBING.
          session.pending = { type: 'advance', id: 'req-1' };
          await session.runPending();
          assert.equal(session.state, 'IDLE');

          const abortRec = {
            supported: true, cancel() {},
            start: async () => {},
            finish: async () => { throw new DOMException('Aborted', 'AbortError'); },
          };
          const s4 = new PracticeSession({ api, recorder: abortRec, player: noopPlayer });
          s4.snapshot = { sessionId: 's4', maxAnswers: 3, pendingStage: null, attempts: [{ number: 1, messages: [{ role: 'assistant', content: 'Q?' }], feedback: null }] };
          await s4.startRecording();
          await s4.finishRecording();
          assert.equal(s4.state, 'IDLE');
        }

        // 4. Non-retryable UNSUPPORTED_AUDIO & PRACTICE_NOT_FOUND clear pending; hearExample respects voiceEnabled.
        {
          const api = {
            transcribe: async () => { const e = new Error('Bad mime'); e.code = 'UNSUPPORTED_AUDIO'; throw e; },
            advance: async () => { const e = new Error('Expired'); e.code = 'PRACTICE_NOT_FOUND'; throw e; },
          };
          const session = new PracticeSession({ api, recorder: noopRecorder, player: noopPlayer });
          session.pending = { type: 'transcribe', audio: new Blob(['x']) };
          await session.runPending();
          assert.equal(session.pending, null);

          session.pending = { type: 'advance', id: 'req-2' };
          await session.runPending();
          assert.equal(session.pending, null);

          session.state = 'IDLE';
          session.voiceEnabled = false;
          session.snapshot = { sessionId: 's5', maxAnswers: 3, attempts: [{ number: 1, messages: [{ role: 'user', content: 'Hi' }], feedback: { improvedMessage: 'Clearer.' } }] };
          await session.hearExample();
          assert.equal(session.pending, null);
        }
        """
    )


def test_web_index_html_apple_hig_structure_and_accessibility():
    import re

    html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert '<meta name="color-scheme" content="light dark">' in html
    assert '<section class="intro"' not in html
    assert 'class="composer-dock"' in html
    assert 'id="turn-steps"' in html
    assert 'id="i-send"' in html

    for required_id in (
        "theme-auto", "theme-light", "theme-dark",
        "brief-mode-brief", "brief-mode-edit", "scene-brief", "scene-toggle",
        "facts-error", "goal-error",
        "how-button", "setup-button", "voice-enabled",
        "context-form", "discipline", "facts", "goal", "familiarity", "reset-scene-button",
        "start-button", "record-button", "done-button", "play-button", "continue-button", "finish-button",
        "stop-button", "reset-button", "answer-text", "send-button",
        "starter-bar", "starter-full", "voice-notice", "retry-voice-button", "mute-voice-button", "dismiss-voice-button",
        "feedback", "hear-example", "retry-button", "comparison",
    ):
        assert f'id="{required_id}"' in html, f"Missing required id={required_id}"

    # Spoken replies toggle belongs inside the header/workspace rather than buried in a footer.
    header_html = html[html.index("<header"):html.index("</header>")]
    assert 'id="voice-enabled"' in header_html

    # Explicit button types & dialog aria-labelledby contracts + strict CSP (no inline styles/scripts).
    for open_tag in re.findall(r"<button\b[^>]*>", html):
        assert 'type="button"' in open_tag or 'type="submit"' in open_tag, f"Button missing explicit type: {open_tag}"
    for dialog_tag in re.findall(r"<dialog\b[^>]*>", html):
        match = re.search(r'aria-labelledby="([^"]+)"', dialog_tag)
        assert match and f'id="{match.group(1)}"' in html, f"Dialog missing valid aria-labelledby: {dialog_tag}"
    assert "style=" not in html and "<style" not in html and html.count("<script") == 1


def test_web_styles_css_apple_system_blue_glass_tokens_and_qa_fixes():
    css = (PROJECT_ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    css_lower = css.lower()

    assert "#007aff" in css_lower and "#0a84ff" in css_lower
    assert "-apple-system" in css and "BlinkMacSystemFont" in css and "SF Pro Display" in css
    assert '[data-theme="dark"]' in css and '[data-theme="light"]' in css and "prefers-color-scheme: dark" in css
    assert "backdrop-filter:" in css and "saturate(180%)" in css
    assert "prefers-reduced-transparency" in css
    assert "clip-path: inset(50%)" in css

    for selector in (".segmented-control", ".composer-dock", ".setting-row", ".field-error", ".scene-toggle", ".turn-progress", ".scene-brief"):
        assert selector in css, f"Missing CSS rules for {selector}"


def test_web_app_js_apple_hig_controls_and_bug_fixes():
    app = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")

    # 1. Safe optional chaining for previous.feedback in renderComparison
    assert "previous?.feedback?.retryFocus" in app

    # 2. Prevent premature coaching header while paused and hide finish-button in coach stage
    assert "const coaching = Boolean(state.feedback) || (state.serverStage === 'coach' && state.state === 'THINKING');" in app
    assert "$('finish-button').hidden = !active || Boolean(state.feedback) || state.serverStage === 'coach';" in app

    # 3. Apple HIG controls: theme switcher, Brief|Customize, mobile scene toggle, 3-step progress, inline validation
    for required_token in (
        "theme-auto",
        "theme-light",
        "theme-dark",
        "dataset.theme",
        "brief-mode-brief",
        "brief-mode-edit",
        "scene-brief",
        "scene-toggle",
        "turn-steps",
        "facts-error",
        "goal-error",
        "noValidate = true",
    ):
        assert required_token in app, f"Missing {required_token} in web/app.js"

    # 4. Existing UI contract invariants preserved
    assert "setAttribute('aria-busy', state.busy ? 'true' : 'false')" in app
    assert "$('error-panel').focus()" in app
    assert "autoResize" in app
    assert "session.queuedAnswer = null" in app


def test_prioritized_ui_fixes_from_browser_qa():
    html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    app = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")

    # UI-1: Headings must not split mid-word or wrap letter-by-letter
    assert '<span class="small-label">SCENARIO</span>' not in html
    assert ".panel-heading h2 {" in css and "white-space: nowrap" in css and "overflow-wrap: normal" in css

    # UI-2: WCAG AA contrast for filled blue controls and small accent text while retaining System Blue
    assert "--accent-fill: #0066d6;" in css
    assert "--accent-ink:" in css

    # UI-3: Audience prefers <select> never hard-clips label text
    assert "text-overflow: ellipsis" in css

    # UI-4 & UI-7: Composer hint handles ERROR separately, avoids stale 'above' direction, and disables stop when idle
    assert "state.state === 'ERROR'" in app
    assert "Start practice above" not in app
    assert "Continue practice above" not in app
    assert "$('stop-button').disabled = !state.busy;" in app

    # UI-5: Keep #reset-button & #stop-button visible in COACHING without empty dock artifact
    assert 'id="coaching-dock-note"' in html
    assert "$('send-button').hidden = Boolean(state.feedback);" in app
    assert ".type-answer[hidden] + .composer-actions" in css
    assert html.index('id="type-answer"') < html.index('id="reset-button"')
    assert html.index('id="answer-form"') < html.index('id="type-answer"') < html.index('id="reset-button"') < html.index("</form>", html.index('id="answer-form"'))

    # UI-6: Tablet sticky .context-card fits viewport height with internal scroll
    assert "max-height: calc(100vh - 88px);" in css

    # UI-7: Header setup pill reflects Live practice vs Test mode
    assert 'id="setup-badge-label"' in html
    assert "Live practice" in app and "Test mode" in app


def test_conversation_default_home_and_separate_scene_and_coach_toggles():
    html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    app = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")

    # Home screen defaults to centered conversation with both side panels collapsed
    assert 'id="workspace" data-scene-open="false" data-coach-open="false"' in html
    assert 'id="context-panel" aria-labelledby="context-heading" hidden' in html
    assert 'id="coach-panel" aria-labelledby="coach-heading" hidden' in html

    # Separate accessible toggle buttons + close buttons in side panel headers
    assert 'id="scene-toggle" aria-expanded="false" aria-controls="context-panel"' in html
    assert 'id="coach-toggle" aria-expanded="false" aria-controls="coach-panel"' in html
    assert 'id="coach-toggle-badge"' in html
    assert 'id="close-scene-button"' in html
    assert 'id="close-coach-button"' in html

    # Responsive grid adapts to open/closed side panels without overlapping or hidden desktop toggles
    assert '.workspace[data-scene-open="true"][data-coach-open="false"]' in css
    assert '.workspace[data-scene-open="false"][data-coach-open="true"]' in css
    assert '.workspace[data-scene-open="true"][data-coach-open="true"]' in css
    assert '.panel-toggle' in css

    # JS wires separate toggles, close buttons, auto-open on invalid scene / ready coaching feedback
    for token in (
        'setSceneOpen',
        'setCoachOpen',
        'close-scene-button',
        'close-coach-button',
        'coach-toggle',
        'coach-toggle-badge',
    ):
        assert token in app, f"Missing {token} in web/app.js"


def test_max_answers_is_ten_across_server_and_ui():
    from server.models import MAX_ANSWERS
    from server.scenario import SCENARIO

    assert MAX_ANSWERS == 10
    assert SCENARIO["maxAnswers"] == 10

    html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    session_js = (PROJECT_ROOT / "web" / "session.js").read_text(encoding="utf-8")
    app_js = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "0 / 10 answers" in html
    assert "one to ten answers" in html
    assert "maxAnswers || 10" in session_js
    assert "maxAnswers || 10" in app_js


def test_churn_pitch_and_two_day_delay_without_pdf_export():
    from server.scenario import DEFAULT_CONTEXT, SCENARIO, SCENARIOS, get_scenario

    assert SCENARIO["id"] == "churn-pitch"
    assert DEFAULT_CONTEXT["scenarioId"] == "churn-pitch"
    assert DEFAULT_CONTEXT["discipline"] == "AI/ML engineer"
    assert [s["id"] for s in SCENARIOS[:2]] == ["churn-pitch", "two-day-delay"]
    assert get_scenario("two-day-delay")["stakeholder"] == "Project manager"

    for path in ("server/scenario.py", "server/prompts.py", "server/providers.py", "web/index.html", "web/app.js"):
        content = (PROJECT_ROOT / path).read_text(encoding="utf-8").lower()
        assert "pdf export" not in content, f"PDF export reference still present in {path}"
        assert "release-update" not in content, f"release-update reference still present in {path}"

    html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="scenario"' in html
    assert 'Customer churn' in html


@pytest.mark.anyio
async def test_natural_closing_sentence_triggers_coaching_and_chains_in_session(context):
    import json
    import httpx
    from server.providers import Providers
    from server.sessions import PracticeStore
    from conftest import ANSWER, feedback_value

    history = [{"role": "assistant", "content": "How is the project going?"}, {"role": "user", "content": ANSWER}]
    def handler(request):
        body = json.loads(request.content)
        is_roleplay = "simulated workplace stakeholder" in body["system_instruction"]
        payload = {"reply": "Sounds great, let us proceed with that plan.", "closed": True} if is_roleplay else feedback_value(history)
        return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(payload)}]}]})

    provider = Providers(
        __import__("server.config", fromlist=["Settings"]).Settings(gemini_key="k"),
        transport=httpx.MockTransport(handler),
        fallback_enabled=False,
    )
    store = PracticeStore()
    session_id = store.create(context, "req-create-1")["sessionId"]
    store.get(session_id).attempt.messages.extend(history)
    snap = await store.advance(session_id, "req-adv-1", provider)
    assert snap["pendingStage"] == "coach"
    assert snap["attempts"][0]["messages"][-1]["content"] == "Sounds great, let us proceed with that plan."

    run_node_module(
        """
        import assert from 'node:assert/strict';
        import { PracticeSession } from './web/session.js';

        let adv = 0;
        const api = {
          create: async () => ({ sessionId: 'sc1', maxAnswers: 10, pendingStage: 'roleplay', attempts: [{ number: 1, messages: [], feedback: null }], playback: null }),
          advance: async () => {
            adv++;
            if (adv === 1) return { sessionId: 'sc1', maxAnswers: 10, pendingStage: 'coach', attempts: [{ number: 1, messages: [{ role: 'user', content: 'Thanks!' }, { role: 'assistant', content: 'Aligned, see you next week.' }], feedback: null }], playback: { text: 'Aligned, see you next week.', speaker: 'VP of Operations' } };
            return { sessionId: 'sc1', maxAnswers: 10, pendingStage: null, attempts: [{ number: 1, messages: [{ role: 'user', content: 'Thanks!' }, { role: 'assistant', content: 'Aligned, see you next week.' }], feedback: { strength: { title: 'Clear', quote: 'Thanks!', reason: 'Direct' }, improvements: [], improvedMessage: 'Thanks!', summary: 'Good.', retryFocus: 'Keep clear.', missingFacts: [], comparison: '' } }], playback: null };
          },
          stop: async () => ({}), reset: async () => ({}),
        };
        const session = new PracticeSession({ api, recorder: { supported: false, cancel() {} }, player: { stop() {}, play: async () => {} } });
        await session.start({ scenarioId: 'churn-pitch' });
        assert.equal(adv, 2);
        assert.ok(session.feedback);
        """
    )






