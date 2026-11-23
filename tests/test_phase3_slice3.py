from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_difficulty_and_auto_silence_controls_present_in_html_and_styles():
    html = source("web/index.html")
    css = source("web/styles.css")

    assert 'id="difficulty" name="difficulty"' in html
    for diff_id in ("supportive", "standard", "skeptical"):
        assert f'value="{diff_id}"' in html

    assert 'id="auto-silence"' in html
    assert "Auto-send on pause" in html
    assert 'id="use-example-button"' in html
    assert "Retry with example draft" in html

    assert ".auto-silence-toggle" in css
    assert ".mic-pill.is-speaking" in css
    assert ".checklist-comparison" in css
    assert ".checklist-badge.is-improved" in css


def test_app_js_wires_difficulty_vad_checklist_comparison_and_example_recovery():
    app = source("web/app.js")
    session = source("web/session.js")

    for token in (
        "function selectedDifficulty()",
        "difficulty: $('difficulty')?.value || 'standard'",
        "DEFAULT_CHECKLIST_DIMENSIONS",
        "checklistGrid.id = 'checklist-comparison'",
        "badgeText = 'Improved ✓'",
        "badgeText = 'Focus next'",
        "$('auto-silence')?.addEventListener('change', event => session.setAutoStopSilence(event.target.checked));",
        "$('use-example-button')?.addEventListener('click'",
        "state.lastTranscribedText",
    ):
        assert token in app, f"Missing {token} in web/app.js"

    assert "this.lastTranscribedText = result.text.trim();" in session
