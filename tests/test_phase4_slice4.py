import json
from pathlib import Path

import httpx
import pytest

from server.app import create_app
from server.config import Settings
from server.providers import Providers
from server.scenario import get_scenario
from tests.test_phase3_slice1 import TEST_SETTINGS, gemini_json_response

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_phase4_pwa_completion_gate_ai_ml_and_hr_retry_with_access_and_rate_limits():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        payload = json.loads(body["input"])
        if "history" in payload:
            return gemini_json_response({"reply": "What is the key boundary and recommended next step?", "closed": False})

        is_retry = payload.get("previousAttempt") is not None
        scenario_id = payload["context"]["scenarioId"]
        user_quote = next(turn["content"] for turn in payload["currentAttempt"] if turn["role"] == "user")
        if scenario_id == "ai-ml-limits":
            improved = "In 100 reviewed test examples, 10 results needed correction, and performance on live customer data has not been established. I recommend starting with a limited pilot with human review."
        else:
            improved = "I automated the weekly operational report and wrote handover notes so the team can run it without manual rebuilding. Time savings have not been measured yet."

        return gemini_json_response({
            "strength": {
                "title": "Grounded explanation",
                "quote": user_quote,
                "reason": "Kept boundaries and facts accurate.",
            },
            "improvements": [
                {
                    "dimension": "Assertiveness" if not is_retry else "Accuracy and next steps",
                    "quote": user_quote,
                    "reason": "Clarify recommendation and limits together.",
                    "suggestion": "Keep the next decision explicit while preserving unmeasured boundaries.",
                }
            ],
            "improvedMessage": improved,
            "summary": "Clear summary keeping limits intact.",
            "retryFocus": "Maintain clear recommendation and boundaries.",
            "missingFacts": [],
            "comparison": "Checklist progress updated across Assertiveness and Accuracy and next steps." if is_retry else "",
        })

    settings = Settings(**{
        **TEST_SETTINGS.__dict__,
        "gemini_key": "test-gemini-key",
        "allowed_hosts": ("demo.devbridge.test",),
        "demo_access_token": "phase4-gate-token",
        "rate_limit_per_minute": 50,
    })
    app = create_app(
        settings_loader=lambda: settings,
        provider_factory=lambda s: Providers(s, transport=httpx.MockTransport(handler)),
    )
    headers = {
        "Host": "demo.devbridge.test",
        "Origin": "https://demo.devbridge.test",
        "X-Forwarded-Proto": "https",
        "X-DevBridge-Token": "phase4-gate-token",
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://demo.devbridge.test") as client:
        unauth = await client.post(
            "/api/practice",
            json={"context": get_scenario("ai-ml-limits")["defaultContext"], "requestId": "phase4-gate-unauth-001"},
            headers={"Host": "demo.devbridge.test", "Origin": "https://demo.devbridge.test", "X-Forwarded-Proto": "https"},
        )
        assert unauth.status_code == 401
        assert "strict-transport-security" in unauth.headers

        scenarios_to_verify = [
            ("ai-ml-limits", "In 100 reviewed test examples, 10 results needed correction and live performance is not established."),
            ("hr-contribution", "I automated the weekly operational report and wrote handover notes for the team."),
        ]
        for idx, (scenario_id, user_answer) in enumerate(scenarios_to_verify, start=1):
            ctx = {**get_scenario(scenario_id)["defaultContext"], "difficulty": "skeptical"}
            created = await client.post(
                "/api/practice",
                json={"context": ctx, "requestId": f"phase4-gate-create-{idx}-001"},
                headers=headers,
            )
            assert created.status_code == 200
            assert "strict-transport-security" in created.headers
            sid = created.json()["sessionId"]

            opened = await client.post(f"/api/practice/{sid}/advance", json={"requestId": f"phase4-gate-open-{idx}-0001"}, headers=headers)
            assert opened.status_code == 200

            ans1 = await client.post(
                f"/api/practice/{sid}/answer",
                json={"text": user_answer, "requestId": f"phase4-gate-ans1-{idx}-0001"},
                headers=headers,
            )
            assert ans1.status_code == 200

            fin1 = await client.post(f"/api/practice/{sid}/finish", json={"requestId": f"phase4-gate-fin1-{idx}-0001"}, headers=headers)
            assert fin1.status_code == 200

            coach1 = await client.post(f"/api/practice/{sid}/advance", json={"requestId": f"phase4-gate-coach1-{idx}-01"}, headers=headers)
            assert coach1.status_code == 200
            assert coach1.json()["attempts"][0]["feedback"]["comparison"] == ""

            retried = await client.post(f"/api/practice/{sid}/retry", json={"requestId": f"phase4-gate-retry-{idx}-001"}, headers=headers)
            assert retried.status_code == 200

            await client.post(f"/api/practice/{sid}/advance", json={"requestId": f"phase4-gate-open2-{idx}-001"}, headers=headers)
            await client.post(
                f"/api/practice/{sid}/answer",
                json={"text": user_answer, "requestId": f"phase4-gate-ans2-{idx}-0001"},
                headers=headers,
            )
            await client.post(f"/api/practice/{sid}/finish", json={"requestId": f"phase4-gate-fin2-{idx}-0001"}, headers=headers)
            coach2 = await client.post(f"/api/practice/{sid}/advance", json={"requestId": f"phase4-gate-coach2-{idx}-01"}, headers=headers)
            assert coach2.status_code == 200
            assert len(coach2.json()["attempts"]) == 2
            assert "Checklist progress" in coach2.json()["attempts"][1]["feedback"]["comparison"]


def test_phase4_validation_report_and_agents_md_documented():
    report = source("docs/PHASE_4_PWA_VALIDATION.md")
    agents = source("agents.md")

    for token in ("manifest.webmanifest", "sw.js", "#offline-notice", "DEMO_ACCESS_TOKEN", "RATE_LIMIT_PER_MINUTE", "DEV-36"):
        assert token in report, f"Missing {token} in docs/PHASE_4_PWA_VALIDATION.md"
        assert token in agents, f"Missing {token} in agents.md"
