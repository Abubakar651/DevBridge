import json
from pathlib import Path
import uuid

import httpx
import pytest

from server.app import create_app
from server.config import Settings
from server.errors import AppError
from server.models import Context, validate_feedback
from server.providers import Providers
from server.scenario import SCENARIO_BY_ID, SCENARIOS
from server.sessions import PracticeStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def key():
    return str(uuid.uuid4())


def test_client_and_it_scenarios_registered_in_backend_and_html():
    ids = [s["id"] for s in SCENARIOS]
    assert "client-scope-change" in ids
    assert "it-ops-handoff" in ids

    html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert '<option value="client-scope-change">Clarifying a client scope change</option>' in html
    assert '<option value="it-ops-handoff">IT handoff &amp; rollout blockers</option>' in html

    for sid, expected_persona in (("client-scope-change", "client"), ("it-ops-handoff", "it-manager")):
        scenario = SCENARIO_BY_ID[sid]
        assert scenario["personaId"] == expected_persona
        assert len(scenario["steps"]) == 3
        assert set(scenario["starters"]) == {"full", "ready", "tradeoff", "recommend"}
        assert set(scenario["starterLabels"]) == {"full", "ready", "tradeoff", "recommend"}
        ctx = Context.model_validate(scenario["defaultContext"])
        assert ctx.scenario_id == sid


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("scenario_id", "expected_speaker", "expected_persona_id"),
    [
        ("client-scope-change", "Client", "client"),
        ("it-ops-handoff", "IT manager", "it-manager"),
    ],
)
async def test_client_and_it_scenarios_run_end_to_end_with_correct_persona(scenario_id, expected_speaker, expected_persona_id):
    scenario = SCENARIO_BY_ID[scenario_id]
    user_answer = scenario["starters"]["full"]
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        is_roleplay = "simulated workplace stakeholder" in body["system_instruction"]
        if is_roleplay:
            payload = {"reply": "Could you clarify the trade-off for our next step?", "closed": False}
        else:
            payload = {
                "strength": {"title": "Clear structure", "quote": user_answer[:80], "reason": "Leads with status and options."},
                "improvements": [{"dimension": "Accuracy and next steps", "quote": user_answer[:80], "reason": "State unapproved status explicitly.", "suggestion": "Confirm what still needs sign-off."}],
                "improvedMessage": user_answer,
                "summary": "Clear summary of status and trade-offs.",
                "retryFocus": "Keep unapproved decisions explicit.",
                "missingFacts": [],
                "comparison": "",
            }
        return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(payload)}]}]})

    provider = Providers(Settings(gemini_key="private-gemini"), transport=httpx.MockTransport(handler), fallback_enabled=False)
    store = PracticeStore()
    ctx = Context.model_validate(scenario["defaultContext"])
    session_id = store.create(ctx, key())["sessionId"]

    opening = await store.advance(session_id, key(), provider)
    assert opening["playback"]["speaker"] == expected_speaker

    store.answer(session_id, user_answer, key())
    store.finish(session_id, key())
    coached = await store.advance(session_id, key(), provider)
    assert coached["playback"]["speaker"] == "Coach"

    roleplay_payload = json.loads(requests[0]["input"])
    coach_payload = json.loads(requests[1]["input"])
    assert roleplay_payload["stakeholder"] == expected_speaker
    assert roleplay_payload["persona"]["id"] == expected_persona_id
    assert coach_payload["persona"]["id"] == expected_persona_id


def test_client_scope_change_guards_duration_and_unmeasured_impact():
    scenario = SCENARIO_BY_ID["client-scope-change"]
    ctx = Context.model_validate(scenario["defaultContext"])
    quote = scenario["starters"]["ready"]
    history = [{"role": "user", "content": quote}]
    base = {
        "strength": {"title": "Clear status", "quote": quote, "reason": "States ready work clearly."},
        "improvements": [{"dimension": "Audience clarity", "quote": quote, "reason": "Clarify decision options.", "suggestion": "Ask which priority the client prefers."}],
        "improvedMessage": "The agreed billing dashboard is ready for launch. Bulk invoice export needs three additional working days of engineering and verification. I recommend launching the dashboard first—which priority would you prefer?",
        "summary": "Clear separation between ready work and new scope.",
        "retryFocus": "Offer a clear choice without promising unapproved dates.",
        "missingFacts": [],
        "comparison": "",
    }
    assert validate_feedback(base, history, ctx)

    with pytest.raises(AppError) as timing_error:
        validate_feedback({**base, "improvedMessage": "Bulk invoice export will be ready in three working days."}, history, ctx)
    assert "delivery promise" in timing_error.value.validation_hint

    with pytest.raises(AppError) as impact_error:
        validate_feedback({**base, "improvedMessage": "The dashboard is ready and there is no customer impact."}, history, ctx)
    assert "unmeasured customer impact" in impact_error.value.validation_hint


@pytest.mark.anyio
async def test_config_endpoint_returns_client_and_it_scenarios():
    app = create_app(settings_loader=lambda: Settings(gemini_key="private-gemini"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        data = (await client.get("/api/config")).json()
    ids = [item["id"] for item in data["scenarios"]]
    assert ids[:4] == ["churn-pitch", "two-day-delay", "client-scope-change", "it-ops-handoff"]
