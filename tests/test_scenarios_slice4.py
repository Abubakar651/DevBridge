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
from server.scenario import PERSONAS, SCENARIO_BY_ID, SCENARIOS
from server.sessions import PracticeStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def key():
    return str(uuid.uuid4())


def test_all_six_phase2_scenarios_and_all_five_personas_are_covered():
    expected_ids = [
        "churn-pitch",
        "two-day-delay",
        "client-scope-change",
        "it-ops-handoff",
        "ai-ml-limits",
        "hr-contribution",
        "student-simple-model",
        "custom",
    ]
    assert [s["id"] for s in SCENARIOS] == expected_ids

    covered_personas = {s["personaId"] for s in SCENARIOS}
    assert covered_personas == set(PERSONAS)

    html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert '<option value="ai-ml-limits">Explaining AI/ML limits &amp; pilot</option>' in html
    assert '<option value="hr-contribution">Describing personal contribution</option>' in html
    assert '<option value="student-simple-model">Explaining a simple ML model</option>' in html
    assert '<option value="custom">Custom scenario (write your own)</option>' in html

    for sid in ("ai-ml-limits", "hr-contribution", "student-simple-model"):
        scenario = SCENARIO_BY_ID[sid]
        assert len(scenario["steps"]) == 3
        assert set(scenario["starters"]) == {"full", "ready", "tradeoff", "recommend"}
        assert set(scenario["starterLabels"]) == {"full", "ready", "tradeoff", "recommend"}
        assert Context.model_validate(scenario["defaultContext"]).scenario_id == sid

    custom = SCENARIO_BY_ID["custom"]
    assert custom["isCustom"] is True
    assert set(custom["starterLabels"]) == {"full", "ready", "tradeoff", "recommend"}
    custom_ctx = Context.model_validate(
        {
            **custom["defaultContext"],
            "knownFacts": "I trained a YOLOv8 model to flag surface cracks on bottle caps across 400 test images.",
            "goal": "Ask the line supervisor for a 3-day shadow trial before connecting alerts to the conveyor.",
        }
    )
    assert custom_ctx.scenario_id == "custom"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("scenario_id", "expected_speaker", "expected_persona_id"),
    [
        ("ai-ml-limits", "IT manager", "it-manager"),
        ("hr-contribution", "HR representative", "hr-representative"),
    ],
)
async def test_ai_ml_limits_and_hr_contribution_complete_cycle_and_retry(scenario_id, expected_speaker, expected_persona_id):
    scenario = SCENARIO_BY_ID[scenario_id]
    user_answer = scenario["starters"]["full"]
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        is_roleplay = "simulated workplace stakeholder" in body["system_instruction"]
        if is_roleplay:
            payload = {"reply": "Could you share what you recommend as the next step?", "closed": False}
        else:
            payload = {
                "strength": {"title": "Clear boundaries", "quote": user_answer[:80], "reason": "Stays factual and transparent."},
                "improvements": [{"dimension": "Structure and relevance", "quote": user_answer[:80], "reason": "Highlight the main takeaway first.", "suggestion": "State the practical outcome in the opening sentence."}],
                "improvedMessage": user_answer,
                "summary": "Clear, honest framing aligned with the stakeholder.",
                "retryFocus": "Open with the practical takeaway first.",
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

    retried = store.retry(session_id, key())
    assert retried["context"] == scenario["defaultContext"]
    assert len(retried["attempts"]) == 2 and retried["attempts"][1]["messages"] == []

    roleplay_payload = json.loads(requests[0]["input"])
    coach_payload = json.loads(requests[1]["input"])
    assert roleplay_payload["stakeholder"] == expected_speaker
    assert roleplay_payload["persona"]["id"] == expected_persona_id
    assert coach_payload["persona"]["id"] == expected_persona_id


def test_ai_ml_limits_and_hr_contribution_grounding_guards():
    ai_scenario = SCENARIO_BY_ID["ai-ml-limits"]
    ai_ctx = Context.model_validate(ai_scenario["defaultContext"])
    ai_quote = ai_scenario["starters"]["ready"]
    ai_base = {
        "strength": {"title": "Honest test numbers", "quote": ai_quote, "reason": "Reports sample corrections plainly."},
        "improvements": [{"dimension": "Accuracy and next steps", "quote": ai_quote, "reason": "State live limits clearly.", "suggestion": "Recommend a human-reviewed pilot."}],
        "improvedMessage": "In the 100 examples we checked, 10 results needed correction. We have not established performance on live customer data. I recommend a limited pilot with human review before considering wider use.",
        "summary": "Preserves test-vs-live uncertainty well.",
        "retryFocus": "Keep live uncertainty paired with the pilot recommendation.",
        "missingFacts": [],
        "comparison": "",
    }
    assert validate_feedback(ai_base, [{"role": "user", "content": ai_quote}], ai_ctx)
    with pytest.raises(AppError) as ai_err:
        validate_feedback({**ai_base, "improvedMessage": "The model is proven on live customer data and guaranteed to work."}, [{"role": "user", "content": ai_quote}], ai_ctx)
    assert "unestablished live AI performance" in ai_err.value.validation_hint

    hr_scenario = SCENARIO_BY_ID["hr-contribution"]
    hr_ctx = Context.model_validate(hr_scenario["defaultContext"])
    hr_quote = hr_scenario["starters"]["ready"]
    hr_base = {
        "strength": {"title": "Owns contribution", "quote": hr_quote, "reason": "States personal work directly."},
        "improvements": [{"dimension": "Assertiveness", "quote": hr_quote, "reason": "Highlight the team benefit.", "suggestion": "State how the automation helps teammates."}],
        "improvedMessage": "I automated the weekly operational report and documented the handover, so it can be prepared without rebuilding the spreadsheet manually. We have not measured the time saving yet. My contribution was implementing the automation and making it easier for the team to use.",
        "summary": "Clear ownership without inventing metrics.",
        "retryFocus": "State your role plainly and keep unmeasured savings transparent.",
        "missingFacts": [],
        "comparison": "",
    }
    assert validate_feedback(hr_base, [{"role": "user", "content": hr_quote}], hr_ctx)
    with pytest.raises(AppError) as hr_err:
        validate_feedback({**hr_base, "improvedMessage": "There are no time savings from this automation."}, [{"role": "user", "content": hr_quote}], hr_ctx)
    assert "unmeasured savings" in hr_err.value.validation_hint

    st_scenario = SCENARIO_BY_ID["student-simple-model"]
    st_ctx = Context.model_validate(st_scenario["defaultContext"])
    st_quote = st_scenario["starters"]["ready"]
    st_base = {
        "strength": {"title": "Plain explanation", "quote": st_quote, "reason": "Describes what the model sorts without jargon."},
        "improvements": [{"dimension": "Accuracy and next steps", "quote": st_quote, "reason": "Keep test mistakes and live uncertainty explicit.", "suggestion": "Ask for a one-week manual check on real messages."}],
        "improvedMessage": st_scenario["starters"]["full"],
        "summary": "Clear summary keeping test limits and unmeasured savings honest.",
        "retryFocus": "Pair test numbers with the one-week manual check ask.",
        "missingFacts": [],
        "comparison": "",
    }
    assert validate_feedback(st_base, [{"role": "user", "content": st_quote}], st_ctx)
    with pytest.raises(AppError) as st_live_err:
        validate_feedback({**st_base, "improvedMessage": "The model is proven on live messages."}, [{"role": "user", "content": st_quote}], st_ctx)
    assert "unestablished live AI performance" in st_live_err.value.validation_hint
    with pytest.raises(AppError) as st_save_err:
        validate_feedback({**st_base, "improvedMessage": "There are no time savings from using the model."}, [{"role": "user", "content": st_quote}], st_ctx)
    assert "unmeasured savings" in st_save_err.value.validation_hint


@pytest.mark.anyio
async def test_config_exposes_all_six_scenarios():
    app = create_app(settings_loader=lambda: Settings(gemini_key="private-gemini"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        data = (await client.get("/api/config")).json()
    assert len(data["scenarios"]) == 8
    assert len(data["personas"]) == 5
