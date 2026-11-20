# Post-Fix Browser Console & Network Summary (Updated 2026-11-19 10:39 Asia/Karachi)

Target: `http://127.0.0.1:4317/` (Chrome `155.0.0.0`, `X11; Linux x86_64`, `evaluate_script` denied by user config)

## Console Audit (Final Pass, Verbatim Findings)
- **Voice Coach / DevBridge application JavaScript:** **0** uncaught JS errors, **0** warnings, **0** unhandled promise rejections across all flows (`1440×900`, `1024×768`, `390×844`, `360×800`).
- **Expected TTS Rate-Limit HTTP Logs (handled non-blockingly):**
  - `Failed to load resource: the server responded with a status of 429 (Too Many Requests)` on `POST http://127.0.0.1:4317/api/speak` after initial Answer 1 WAV succeeded (`audio/wav` played via `GET blob:... [206]`). Handled gracefully by `#voice-notice` without locking `#answer-text`, `#send-button`, `#record-button`, or `#starter-bar`.
- **Browser Extension Noise / CSP (`chrome-extension://invalid/`):**
  - `Failed to load resource: net::ERR_FAILED [8 times]` (Grammarly/QuillBot extension `HEAD chrome-extension://invalid/` probes).
  - `Content Security Policy of your site blocks the use of eval in JavaScript` (`script-src 'self'`, extension-context `eval` blocked cleanly by strict CSP).

## Network Verification Highlights
- **Initial / reload assets (`ignoreCache=true`):** `/`, `/styles.css`, `/app.js`, `/api.js`, `/audio.js`, `/session.js`, `/api/config`, `/icon.svg` -> all HTTP `200 OK`.
- **Pre-start direct chat submission (`startWithAnswer`):** Typing into `#answer-text` on initial load and pressing `Enter` executed `POST /api/practice` (`200`) → `POST /advance` (`200`) → `POST /answer` (`200`) → `POST /advance` (`200`) seamlessly.
- **Voice Notice Actions:** Verified `Retry audio` (`POST /api/speak`), `Dismiss` (`×`), and `Turn voice off` (`#mute-voice-button`), plus `Stop` during `THINKING` (`POST /stop` `200`) + `Continue practice` (`POST /advance` `200`).
- **Single-Request Reset (`#reset-button`):** Verified single `DELETE /api/practice/{id}` (`204`) with zero competing `POST /stop` requests.
