# Browser Console, Network & Security Header Evidence (Sanitized)

Captured in Chrome 155 (`Chrome/155.0.0.0`, Linux x86_64) against `http://127.0.0.1:4317` across Part 1, Part 2A, and Part 2B on 2026-11-19 (Asia/Karachi).

## Security Headers Verified on `/`, Static Assets, and `/api/config`
- `content-security-policy`: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`
- `permissions-policy`: `microphone=(self), camera=()`
- `referrer-policy`: `no-referrer`
- `x-content-type-options`: `nosniff`
- `cache-control`: `no-store`

## Console Messages
- Initial page load: 0 console errors, 0 warnings, 0 unhandled rejections.
- After focusing textareas (Grammarly / QuillBot browser extensions installed in test browser):
  - `Content Security Policy of your site blocks the use of eval in JavaScript` (`violatedDirective: "script-src"`, `kEvalViolation` — blocked third-party extension `eval`, not Voice Coach code).
  - `Failed to load resource: net::ERR_FAILED` (8x, corresponding to browser extension `HEAD chrome-extension://invalid/` probes).
- Application-initiated HTTP error tests (expected):
  - 2x `400 Bad Request` during intentional 20-space `#facts` validation test (`POST /api/practice` -> `INVALID_INPUT`).
  - Live Groq upstream errors during Part 2A recovery check: `502` (`INVALID_PROVIDER_OUTPUT`) and `429` (`PROVIDER_RATE_LIMIT`), both rendered cleanly in `#error-panel` and recovered on retry.
- Voice Coach uncaught JS exceptions or unhandled promise rejections: **0**.

## Key Network Observations
- Static load (`GET /`, `/styles.css`, `/app.js`, `/api.js`, `/audio.js`, `/session.js`, `/icon.svg`): all HTTP 200.
- `GET /api/config`: HTTP 200, returned key-presence booleans (`{"gemini": true, "groq": true, "coaching": true, "speech": true}`) with zero secrets.
- Voice recording & playback (Part 1 & Part 2A):
  - `MediaRecorder` selected `audio/webm;codecs=opus`.
  - `POST /api/transcribe` (`audio/webm;codecs=opus`, 277,349 B and 145,541 B): HTTP 200 with real Whisper transcripts.
  - `POST /api/speech/segments`: HTTP 200 (1 segment for roleplay replies; 2 segments for `Hear the example` > 200 chars).
  - `POST /api/speak`: HTTP 200 (`audio/wav`, 280,390 B; 326,470 B; 468,550 B; 330,310 B), played sequentially via `blob:` URLs (`GET blob:...` HTTP 206) without `NotAllowedError`.
- Stop / Reset / Page reload:
  - Clicking `#stop-button` during `THINKING` / `SYNTHESIZING` / `SPEAKING` aborted in-flight browser fetch (`net::ERR_ABORTED`) and sent `POST /api/practice/{id}/stop` (HTTP 200).
  - Clicking `#reset-button` sent both `POST /api/practice/{id}/stop` (HTTP 200) and `DELETE /api/practice/{id}` (HTTP 204; DevTools displayed `net::ERR_ABORTED` alongside Status 204 for empty `keepalive: true` 204 response).
  - Reloading during active session showed `GET /` [200] directly after `GET blob:...` [206] in DevTools preserved logs with no `DELETE` captured in DevTools UI; reloaded tab started fresh (`0 / 3 answers`).
