import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_mobile_help_and_accessible_status_survive_the_responsive_layout():
    page = source("web/index.html")
    styles = source("web/styles.css")
    app = source("web/app.js")

    assert 'id="how-button"' in page
    assert '.site-header nav { display: none' not in styles
    assert 'id="configuration-notice" class="notice" role="status"' in page
    assert 'id="error-panel" class="error-panel" role="alert" tabindex="-1"' in page
    assert "setAttribute('aria-busy', state.busy ? 'true' : 'false')" in app
    assert "$('error-panel').focus()" in app


def test_ui_uses_readable_controls_and_non_decorative_actions():
    page = source("web/index.html")
    styles = source("web/styles.css")

    assert re.search(r":root\s*\{.*?font-size:\s*16px", styles, re.S)
    assert ".icon-button { min-width: 44px; min-height: 44px;" in styles
    assert ".button { min-height: 46px;" in styles
    assert "appearance: none" in styles and "background-image: url(" in styles
    assert "section-number" not in page and "note-number" not in page
    assert "↗" not in page
    for button in re.findall(r"<button\b.*?</button>", page, re.S):
        assert '#i-arrow' not in button


def test_short_audience_labels_preserve_the_context_values():
    page = source("web/index.html")

    assert '<option value="Business-focused; prefers plain language">Plain language, business focused</option>' in page
    assert '<option value="Some technical context; explain trade-offs">Some technical context</option>' in page


def test_easy_start_cues_and_controls_preserve_button_contract():
    page = source("web/index.html")
    styles = source("web/styles.css")
    app = source("web/app.js")
    session = source("web/session.js")

    assert 'id="starter-bar"' in page
    assert 'id="starter-full"' in page
    assert 'id="reset-scene-button"' in page
    assert 'class="easy-start-steps"' in page
    assert '<details class="type-answer"' not in page
    assert 'id="voice-notice"' in page
    assert 'id="retry-voice-button"' in page
    assert 'id="mute-voice-button"' in page
    assert 'id="dismiss-voice-button"' in page
    assert 'field-sizing: content' in styles
    assert 'autoResize' in app
    assert 'startWithAnswer' in session and 'this.voiceError =' in session
    for button in re.findall(r"<button\b.*?</button>", page, re.S):
        assert '#i-arrow' not in button
