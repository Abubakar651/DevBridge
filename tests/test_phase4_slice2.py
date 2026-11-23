import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_offline_notice_banner_and_styles_present():
    html = source("web/index.html")
    css = source("web/styles.css")

    assert 'id="offline-notice"' in html
    assert 'class="notice offline-notice"' in html
    btn_match = re.search(r'<button\b[^>]*id="offline-retry-button"[^>]*>', html)
    assert btn_match, "Expected #offline-retry-button in web/index.html"
    assert 'type="button"' in btn_match.group(0)
    assert ".offline-notice" in css


def test_app_js_wires_offline_detection_and_service_worker_registration():
    app = source("web/app.js")
    for token in (
        "function syncOfflineUI()",
        "window.addEventListener('offline'",
        "window.addEventListener('online'",
        "navigator.serviceWorker.register('/sw.js'",
        "isOffline",
    ):
        assert token in app, f"Missing {token} in web/app.js"
