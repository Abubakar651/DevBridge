import json
import uuid

import httpx
import pytest
from pydantic import ValidationError

from server.app import create_app
from server.config import Settings
from server.errors import AppError
from server.models import Context, validate_feedback
from server.prompts import COACH_PROMPT, ROLEPLAY_PROMPT
from server.providers import Providers
from server.scenario import FAMILIARITY_OPTIONS, PERSONA_BY_ID, PERSONA_LIST, PERSONAS, SCENARIO_BY_ID, resolve_persona
from server.sessions import PracticeStore
from conftest import ANSWER, QUESTION, TEST_CONTEXT, feedback_value


def key():
    return str(uuid.uuid4())


def test_persona_registry_and_familiarity_options_cover_all_five_stakeholders():
    assert list(PERSONAS) == ["vp-ops", "project-manager", "client", "it-manager", "hr-representative"]
    assert len(PERSONA_LIST) == 5
    required_keys = {
        "id",
        "label",
        "tag",
        "avatar",
        "priorities",
        "noticesFirst",
        "evidenceBar",
        "openingStyle",
        "pushbackTriggers",
        "coachingFocus",
    }
    for persona in PERSONA_LIST:
        assert required_keys.issubset(persona.keys())
        assert all(isinstance(persona[k], str) and persona[k].strip() for k in required_keys)

    assert [opt["label"] for opt in FAMILIARITY_OPTIONS] == [
        "Plain language, business focused",
        "Some technical context",
        "Technical lead (architecture ok)",
    ]


@pytest.mark.anyio
async def test_config_exposes_personas_and_familiarity_options_cleanly():
    app = create_app(settings_loader=lambda: Settings(gemini_key="private-gemini"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        data = (await client.get("/api/config")).json()
    assert [p["id"] for p in data["personas"]] == ["vp-ops", "project-manager", "client", "it-manager", "hr-representative"]
    assert data["familiarityOptions"] == FAMILIARITY_OPTIONS
    assert "personaId" not in data["defaultContext"]


def test_context_validates_dynamic_scenarios_and_optional_persona_id():
    base = Context.model_validate(TEST_CONTEXT)
    assert base.persona_id is None
    assert "personaId" not in base.model_dump(by_alias=True, exclude_none=True)

    mixed = Context.model_validate({**TEST_CONTEXT, "scenarioId": "churn-pitch", "personaId": "it-manager"})
    assert mixed.scenario_id == "churn-pitch"
    assert mixed.persona_id == "it-manager"
    assert mixed.model_dump(by_alias=True, exclude_none=True)["personaId"] == "it-manager"

    assert resolve_persona("churn-pitch")["id"] == "vp-ops"
    assert resolve_persona("churn-pitch", "client")["label"] == "Client"
    assert SCENARIO_BY_ID["two-day-delay"]["personaId"] == "project-manager"

    with pytest.raises(ValidationError):
        Context.model_validate({**TEST_CONTEXT, "scenarioId": "unknown-scenario"})
    with pytest.raises(ValidationError):
        Context.model_validate({**TEST_CONTEXT, "personaId": "unknown-persona"})


@pytest.mark.anyio
async def test_api_rejects_unknown_scenario_or_persona_with_400():
    app = create_app(settings_loader=lambda: Settings(gemini_key="private-gemini"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        bad_scenario = await client.post("/api/practice", json={"context": {**TEST_CONTEXT, "scenarioId": "bad-id"}, "requestId": key()})
        bad_persona = await client.post("/api/practice", json={"context": {**TEST_CONTEXT, "personaId": "bad-persona"}, "requestId": key()})
    assert bad_scenario.status_code == 400 and bad_scenario.json()["error"]["code"] == "INVALID_INPUT"
    assert bad_persona.status_code == 400 and bad_persona.json()["error"]["code"] == "INVALID_INPUT"


@pytest.mark.anyio
async def test_mix_and_match_persona_override_flows_through_session_and_providers():
    requests = []
    history = [{"role": "assistant", "content": "How will support handle alerts?"}, {"role": "user", "content": ANSWER}]

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        is_roleplay = "simulated workplace stakeholder" in body["system_instruction"]
        payload = {"reply": QUESTION, "closed": False} if is_roleplay else feedback_value(history)
        return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(payload)}]}]})

    provider = Providers(Settings(gemini_key="private-gemini"), transport=httpx.MockTransport(handler), fallback_enabled=False)
    mixed_ctx = Context.model_validate({**TEST_CONTEXT, "scenarioId": "churn-pitch", "personaId": "it-manager"})

    store = PracticeStore()
    session_id = store.create(mixed_ctx, key())["sessionId"]
    opening = await store.advance(session_id, key(), provider)
    assert opening["playback"]["speaker"] == "IT manager"
    assert opening["context"]["personaId"] == "it-manager"

    store.answer(session_id, ANSWER, key())
    store.finish(session_id, key())
    coached = await store.advance(session_id, key(), provider)
    assert coached["playback"]["speaker"] == "Coach"

    retried = store.retry(session_id, key())
    assert retried["context"]["personaId"] == "it-manager"

    roleplay_payload = json.loads(requests[0]["input"])
    coach_payload = json.loads(requests[1]["input"])
    assert roleplay_payload["stakeholder"] == "IT manager"
    assert roleplay_payload["persona"]["id"] == "it-manager"
    assert "pushbackTriggers" in roleplay_payload["persona"]
    assert coach_payload["persona"]["id"] == "it-manager"
    assert coach_payload["persona"]["coachingFocus"] == PERSONA_BY_ID["it-manager"]["coachingFocus"]
    assert "simulated workplace stakeholder" in ROLEPLAY_PROMPT
    assert "EXACT, contiguous excerpt" in COACH_PROMPT


def test_unmeasured_savings_guard_preserves_uncertainty_across_hr_scenarios():
    hr_context = Context.model_validate(
        {
            "scenarioId": "two-day-delay",
            "personaId": "hr-representative",
            "discipline": "Software developer",
            "familiarity": "Business-focused; prefers plain language",
            "knownFacts": "The weekly report was previously assembled manually in a spreadsheet. I automated its generation and wrote handover notes. Time savings have not been measured.",
            "goal": "Explain personal contribution and team benefit clearly without minimizing work or inventing metrics.",
        }
    )
    user_quote = "I automated the weekly report and documented the handover notes."
    history = [{"role": "user", "content": user_quote}]
    base = {
        "strength": {"title": "Clear ownership", "quote": user_quote, "reason": "States what you delivered plainly."},
        "improvements": [{"dimension": "Accuracy and next steps", "quote": user_quote, "reason": "Mention the measurement limit.", "suggestion": "State clearly that time savings have not been measured yet."}],
        "improvedMessage": "I automated the weekly report and documented the handover, so it can be prepared without rebuilding the spreadsheet manually. We have not measured the time saving yet. My contribution was implementing the automation and making it easier for the team to use.",
        "summary": "Clear personal ownership with honest measurement boundaries.",
        "retryFocus": "Explain practical benefit without minimizing your contribution.",
        "missingFacts": [],
        "comparison": "",
    }
    assert validate_feedback(base, history, hr_context)

    for bad_rewrite in (
        "There are no time savings from this script.",
        "I automated the weekly report and it delivers guaranteed savings.",
    ):
        broken = {**base, "improvedMessage": bad_rewrite}
        with pytest.raises(AppError) as error:
            validate_feedback(broken, history, hr_context)
        assert "unmeasured savings" in error.value.validation_hint


def test_unestablished_live_ai_guard_preserves_testing_boundaries():
    ai_context = Context.model_validate(
        {
            "scenarioId": "churn-pitch",
            "personaId": "it-manager",
            "discipline": "AI/ML engineer",
            "familiarity": "Some technical context; explain trade-offs",
            "knownFacts": "In 100 reviewed test examples, 10 results needed correction. Performance on live customer data has not been established. A reviewed pilot is one option.",
            "goal": "Explain evaluation limits honestly and propose a reviewed pilot.",
        }
    )
    user_quote = "In 100 reviewed test examples, 10 needed correction so we need a reviewed pilot."
    history = [{"role": "user", "content": user_quote}]
    base = {
        "strength": {"title": "Honest test numbers", "quote": user_quote, "reason": "States checked sample limitations directly."},
        "improvements": [{"dimension": "Audience clarity", "quote": user_quote, "reason": "State live uncertainty clearly.", "suggestion": "Note that performance on live customer data has not been established yet."}],
        "improvedMessage": "In the 100 examples we checked, 10 results needed correction. We have not established performance on live customer data. I recommend a limited pilot with human review before considering wider use.",
        "summary": "Strong factual boundary between test samples and live rollout.",
        "retryFocus": "Pair test numbers directly with human-review oversight.",
        "missingFacts": [],
        "comparison": "",
    }
    assert validate_feedback(base, history, ai_context)

    also_safe = {**base, "improvedMessage": "In the 100 examples we checked, 10 results needed correction. It is not proven on live customer data and not ready for full production rollout."}
    assert validate_feedback(also_safe, history, ai_context)

    for bad_rewrite in (
        "The model is proven on live customer data.",
        "With these test results, it is guaranteed to work for customers.",
        "The pipeline is ready for full production rollout.",
    ):
        broken = {**base, "improvedMessage": bad_rewrite}
        with pytest.raises(AppError) as error:
            validate_feedback(broken, history, ai_context)
        assert "unestablished live AI performance" in error.value.validation_hint
