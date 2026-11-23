# Phase 4 Mobile PWA, Offline Shell & Completion Gate Validation

**Status:** Phase 4 Complete (`DEV-36` Workstream: `DEV-37`–`DEV-40`)  
**Date:** 23 November 2026  
**Scope:** Installable PWA manifest/icons, static-shell-only service worker, offline notice & recovery, optional shared-demo access & rate-limit guards, and end-to-end validation including `ai-ml-limits` and `hr-contribution`.

---

## 1. Phase 4 Deliverables Implemented

1. **Installable Web App Manifest & Icons (`DEV-37`):**
   - [`web/manifest.webmanifest`](../web/manifest.webmanifest) configures `display: "standalone"`, `start_url: "/"`, `theme_color: "#007aff"`, `background_color: "#f5f5f7"`, and both standard (`/icon.svg`) and maskable (`/icon-maskable.svg`) SVG icons.
   - [`web/index.html`](../web/index.html) links the manifest, `apple-touch-icon`, and mobile web-app meta tags; [`server/app.py`](../server/app.py) registers `application/manifest+json`.
2. **Static-Shell-Only Service Worker (`DEV-37`, `web/sw.js`):**
   - Pre-caches only the static shell (`/`, `/index.html`, `/styles.css`, `/app.js`, `/api.js`, `/audio.js`, `/session.js`, `/icon.svg`, `/icon-maskable.svg`, `/manifest.webmanifest`) under `devbridge-shell-v1`.
   - Explicitly bypasses all `/api/*`, non-GET, and cross-origin requests (`isStaticShellRequest`) so cloud conversations, transcripts, and keys are never cached.
3. **Offline Detection Banner & Connection Recovery (`DEV-38`):**
   - [`web/index.html`](../web/index.html), [`web/styles.css`](../web/styles.css), and [`web/app.js`](../web/app.js) register `/sw.js` on HTTPS or localhost, surface `#offline-notice` with a *Reconnect* button (`#offline-retry-button`), disable live cloud buttons when offline, and restore config automatically when `online` fires.
4. **HTTPS/Origin Headers, Access Token & Usage Rate Limits (`DEV-39`):**
   - [`server/config.py`](../server/config.py) & [`server/app.py`](../server/app.py) support optional `ALLOWED_HOSTS`, HTTPS / `X-Forwarded-Proto: https` with `Strict-Transport-Security`, constant-time `DEMO_ACCESS_TOKEN` verification (`401 ACCESS_REQUIRED`), and per-IP 60-second sliding-window `RATE_LIMIT_PER_MINUTE` enforcement (`429 RATE_LIMITED`). Zero-config defaults preserve frictionless local dev.

---

## 2. Completion Gate Verification (`ai-ml-limits` & `hr-contribution`)

| Check | Coverage & Observed Result |
| --- | --- |
| **Static Shell & Offline Isolation (`tests/test_phase4_slice1.py`, `test_phase4_slice2.py`)** | `devbridge-shell-v1` serves cached shell assets offline, cleans old caches, and never intercepts `/api/config`, `/api/practice`, `/api/speak`, `/api/transcribe`, or external URLs. `#offline-notice` toggles automatically on `offline`/`online`. |
| **Shared-Demo Security & Rate Limits (`tests/test_phase4_slice3.py`)** | Verified `ALLOWED_HOSTS` + HTTPS HSTS headers, `DEMO_ACCESS_TOKEN` blocking unauthenticated `/api/*` without exposing secrets in `/api/config`, and 60s sliding-window `429` throttling + recovery. |
| **End-to-End Retry Gate (`tests/test_phase4_slice4.py`)** | Complete Attempt 1 -> Coaching -> Retry -> Attempt 2 Checklist Comparison cycles verified for both **`ai-ml-limits`** (IT manager) and **`hr-contribution`** (HR representative) under strict `ALLOWED_HOSTS` + `DEMO_ACCESS_TOKEN` + `RATE_LIMIT_PER_MINUTE` enforcement. |

### Observed Latency Profile & Known Limitations
- **Local FastAPI + Static Shell overhead:** Sub-10ms local request routing and shell asset delivery (`GET /`, `/manifest.webmanifest`, `/sw.js`, `/api/config`). End-to-end role-play/coaching latency is bounded by upstream Gemini/Groq/OpenRouter network RTT (typically 1–4s per turn, guarded by 30s upstream timeout and immediate `AbortController`/Stop cancellation).
- **Cloud requirement:** Offline mode displays the cached UI shell and `#offline-notice`; speech-to-text, LLM coaching, and TTS require an active network connection.
- **Deferred backlog (`DEV-5`):** Replacing Groq Orpheus TTS (`canopylabs/orpheus-v1-english`, 200-char segments) with open-source Kokoro-82M / Piper remains tracked separately in Jira as `DEV-5`.
