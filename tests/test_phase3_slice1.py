import json
from typing import get_args

import httpx
import pytest

from server.app import create_app
from server.config import Settings
from server.models import Context, Dimension
from server.prompts import COACH_PROMPT, ROLEPLAY_PROMPT
from server.providers import Providers
from server.scenario import (
    CHECKLIST_DIMENSIONS,
    DEFAULT_CONTEXT,
    DEFAULT_DIFFICULTY_ID,
    DIFFICULTIES,
    DIFFICULTY_LIST,
    resolve_difficulty,
)

TEST_SETTINGS = Settings(gemini_key="test-gemini-key", groq_key="test-groq-key")


def gemini_json_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "completed",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(payload)}]}],
        },
    )


def test_difficulty_registry_and_checklist_dimensions_cover_phase3_contract():
    assert [item["id"] for item in DIFFICULTY_LIST] == ["supportive", "standard", "skeptical"]
    assert DEFAULT_DIFFICULTY_ID == "standard"
    for item in DIFFICULTY_LIST:
        assert set(item.keys()) == {"id", "label", "tag", "roleplayGuidance", "coachingGuidance"}
        assert all(isinstance(v, str) and v.strip() for v in item.values())

    assert resolve_difficulty(None)["id"] == "standard"
    assert resolve_difficulty("")["id"] == "standard"
    assert resolve_difficulty("unknown")["id"] == "standard"
    assert resolve_difficulty("skeptical")["id"] == "skeptical"

    expected_dimensions = list(get_args(Dimension))
    assert [item["id"] for item in CHECKLIST_DIMENSIONS] == expected_dimensions
    for item in CHECKLIST_DIMENSIONS:
        assert set(item.keys()) == {"id", "label", "description"}
        assert all(isinstance(v, str) and v.strip() for v in item.values())


@pytest.mark.anyio
async def test_config_exposes_difficulties_and_checklist_dimensions():
    app = create_app(settings_loader=lambda: TEST_SETTINGS)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:4317") as client:
        response = await client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["difficulties"]] == ["supportive", "standard", "skeptical"]
    assert [item["id"] for item in payload["checklistDimensions"]] == list(get_args(Dimension))


@pytest.mark.anyio
async def test_context_validates_optional_difficulty_and_rejects_unknown_with_400():
    default_ctx = Context.model_validate(DEFAULT_CONTEXT)
    assert default_ctx.difficulty is None
    assert "difficulty" not in default_ctx.model_dump(by_alias=True, exclude_none=True)

    for diff_id in DIFFICULTIES:
        ctx = Context.model_validate({**DEFAULT_CONTEXT, "difficulty": diff_id})
        assert ctx.difficulty == diff_id
        assert ctx.model_dump(by_alias=True, exclude_none=True)["difficulty"] == diff_id

    app = create_app(settings_loader=lambda: TEST_SETTINGS)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:4317") as client:
        bad = await client.post(
            "/api/practice",
            json={"context": {**DEFAULT_CONTEXT, "difficulty": "hostile"}, "requestId": "bad-diff-001"},
        )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "INVALID_INPUT"


@pytest.mark.anyio
async def test_difficulty_flows_through_session_into_roleplay_and_coach_payloads():
    assert "difficulty.guidance" in ROLEPLAY_PROMPT
    assert "5-dimension communication checklist" in COACH_PROMPT

    captured_inputs = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        payload = json.loads(body["input"])
        captured_inputs.append(payload)
        if "history" in payload:
            return gemini_json_response({"reply": "What fallback plan do we have if CRM alerts fail?", "closed": False})
        return gemini_json_response({
            "strength": {
                "title": "Clear progress summary",
                "quote": "We spent the first four weeks organizing historical customer data",
                "reason": "Opens with concrete work completed.",
            },
            "improvements": [
                {
                    "dimension": "Assertiveness",
                    "quote": "Integrating automated at-risk alerts into the CRM requires four additional working weeks.",
                    "reason": "States effort without a direct approval recommendation.",
                    "suggestion": "Add a clear recommendation asking to approve the four-week CRM phase.",
                }
            ],
            "improvedMessage": "We spent the first four weeks organizing historical customer data and building a churn prediction model. Integrating automated at-risk alerts into the CRM requires four additional working weeks. I recommend approving the four-week CRM integration phase.",
            "summary": "Clear progress; add a direct approval ask.",
            "retryFocus": "End with an explicit approval question.",
            "missingFacts": [],
            "comparison": "",
        })

    transport = httpx.MockTransport(handler)
    settings = Settings(**{**TEST_SETTINGS.__dict__, "gemini_key": "test-gemini-key"})
    app = create_app(
        settings_loader=lambda: settings,
        provider_factory=lambda s: Providers(s, transport=transport),
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:4317") as client:
        created = await client.post(
            "/api/practice",
            json={"context": {**DEFAULT_CONTEXT, "difficulty": "skeptical"}, "requestId": "phase3-slice1-create-001"},
        )
        assert created.status_code == 200
        session_id = created.json()["sessionId"]
        assert created.json()["context"]["difficulty"] == "skeptical"

        opened = await client.post(f"/api/practice/{session_id}/advance", json={"requestId": "phase3-slice1-open-0001"})
        assert opened.status_code == 200

        answered = await client.post(
            f"/api/practice/{session_id}/answer",
            json={
                "text": "We spent the first four weeks organizing historical customer data. Integrating automated at-risk alerts into the CRM requires four additional working weeks.",
                "requestId": "phase3-slice1-answer-001",
            },
        )
        assert answered.status_code == 200

        finished = await client.post(f"/api/practice/{session_id}/finish", json={"requestId": "phase3-slice1-finish-001"})
        assert finished.status_code == 200

        coached = await client.post(f"/api/practice/{session_id}/advance", json={"requestId": "phase3-slice1-coach-0001"})
        assert coached.status_code == 200

    assert len(captured_inputs) == 2
    assert captured_inputs[0]["difficulty"]["id"] == "skeptical"
    assert "high professional scrutiny" in captured_inputs[0]["difficulty"]["guidance"]
    assert captured_inputs[1]["difficulty"]["id"] == "skeptical"
    assert "stakeholder pressure" in captured_inputs[1]["difficulty"]["guidance"]
