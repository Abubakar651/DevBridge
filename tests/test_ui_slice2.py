from pathlib import Path

from server.scenario import SCENARIOS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_persona_selector_third_familiarity_and_neutral_how_dialog():
    html = source("web/index.html")

    assert 'id="persona" name="persona"' in html
    for persona_id in ("vp-ops", "project-manager", "client", "it-manager", "hr-representative"):
        assert f'value="{persona_id}"' in html

    assert '<option value="Business-focused; prefers plain language">Plain language, business focused</option>' in html
    assert '<option value="Some technical context; explain trade-offs">Some technical context</option>' in html
    assert '<option value="Technical lead; architecture &amp; metrics ok">Technical lead (architecture ok)</option>' in html

    assert "simulated stakeholder" in html
    assert "simulated project manager" not in html


def test_app_js_wires_non_destructive_mix_and_match_persona_ui():
    app = source("web/app.js")

    for token in (
        "function selectedPersona()",
        "function syncPersonaUI()",
        "scenario.starterLabels?.[key]",
        "personaId: $('persona')?.value",
        "$('persona').addEventListener('change'",
        "configuration.personas",
        "configuration.familiarityOptions",
    ):
        assert token in app, f"Missing {token} in web/app.js"


def test_scenarios_define_dynamic_starter_labels():
    for scenario in SCENARIOS:
        labels = scenario.get("starterLabels")
        assert isinstance(labels, dict)
        assert set(labels) == {"full", "ready", "tradeoff", "recommend"}
        assert all(isinstance(v, str) and v.strip() for v in labels.values())
