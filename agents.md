# agents.md — DevBridge (Voice Coach)

Comprehensive engineering and product reference for AI coding agents working in `NETSOL/Voice_Coach`.

---

## 1. Product Purpose, Learning Objective & Scope

**DevBridge** (folder name `NETSOL/Voice_Coach` retained for local path compatibility) is a spoken workplace communication coach for **software developers** and **AI/ML engineers**.

- **Goal:** Help engineers explain technical work, reasoning, constraints, AI/ML limitations, and recommendations clearly, confidently, and respectfully to people with less technical context.
- **Confirmed coaching loop:**
  `Role-play the stakeholder -> Give grounded feedback -> Offer an improved explanation -> Practise again`
  Retries keep the exact same scenario facts (`Context`) and store each attempt separately for side-by-side comparison.
- **Target stakeholders (from [Voice_Coach_Project_Plan.pdf](output/pdf/Voice_Coach_Project_Plan.pdf) V3.0):**
  1. **Project manager** — progress updates, dependencies, realistic expectations *(implemented in Phase 1)*.
  2. **Client** — value, feasibility, scope changes, delivery options *(Phase 2)*.
  3. **IT manager** — operational impact, implementation trade-offs, support needs *(Phase 2)*.
  4. **HR representative** — contributions, responsibilities, workload, development goals *(Phase 2)*.
- **5-dimension communication checklist (`Dimension` in `server/models.py`):**
  1. `Audience clarity` — plain language; necessary technical terms explained.
  2. `Structure and relevance` — outcome and business impact before unnecessary implementation detail.
  3. `Assertiveness` — clear position and recommendation; uncertainty stated when justified; polite requests and decision questions remain valid.
  4. `Respect` — avoids blame, dismissiveness, and assumptions about listener intelligence.
  5. `Accuracy and next steps` — facts and limits preserved; next action or needed decision is clear.
- **Superseded legacy scope:** Earlier OOP/SQL technical-interview drills, technical-depth grading, fixed 5-answer interviews, and the old Node/npm backend are superseded. `build_voice_coach_board.py`, `miro_client.py`, and `outputs/board_manifest.json` remain only as historical Miro planning utilities.

---

## 2. Implementation Status vs. Delivery Roadmap

### Implemented Now (Phase 1)
- **Single scenario:** `release-update` ("The release update", Project Manager persona, `server/scenario.py`).
- **Backend (`server/`):** Python 3.12 + FastAPI + Uvicorn + HTTPX + Pydantic. Owns scenario data, prompts, provider integrations, structured-output validation, meaning-preservation guards, in-memory sessions, attempt histories, idempotency, and speech segmentation.
- **Frontend (`web/`):** Plain HTML, CSS, and browser ES modules. No Node runtime, no npm, no bundler.
- **Voice & reasoning pipeline:**
  1. **Capture (`web/audio.js`):** Browser `MediaRecorder` (`Record answer` / `Done speaking`, 60s / 5 MB limit) or always-open text composer (`#answer-text`) + quick starter chips (`#starter-bar`).
  2. **Transcribe (`POST /api/transcribe`):** Groq Whisper (`whisper-large-v3-turbo`).
  3. **Reason (`POST /api/practice/{id}/advance`):** Gemini (`gemini-3.5-flash-lite` via Interactions API, `store=false`) primary, with automatic fallback to Groq (`openai/gpt-oss-20b` via Chat Completions strict JSON schema).
  4. **Speak (`POST /api/speech/segments` + `POST /api/speak`):** Groq Orpheus (`canopylabs/orpheus-v1-english`, voice `troy`, 200-char segment limit, WAV output). TTS failures (`429`, `503`, etc.) degrade non-blockingly via `#voice-notice` without locking text or mic input.

### Planned Later Phases (from `Voice_Coach_Project_Plan.pdf`)
- **Phase 2:** Add Client, IT Manager, and HR personas; software and AI/ML scenario variants (completed work, deadlines/capacity, scope changes, blockers/dependencies, AI/ML limits, contribution/workload); configurable audience familiarity.
- **Phase 3:** Automatic voice-activity/silence detection (retaining manual controls), improved playback recovery & text entry, attempt comparison against the communication checklist, difficulty settings, and qualitative pilot validation.
- **Phase 4:** Mobile PWA (`manifest`, icons, responsive layout, service worker caching static shell only, offline notice, HTTPS delivery, access controls, and server usage limits).

---

## 3. Architecture & Data Flow

```text
Browser (web/)                              Python Server (server/)
──────────────                              ───────────────────────
index.html + styles.css                     run.py / server/runtime.py (.venv)
app.js (DOM, starters, forms)    <─HTTP─>   app.py (FastAPI + LocalMiddleware + cancellable)
session.js (UI state machine)               sessions.py (PracticeStore, Attempt, Lock, generation)
audio.js (Recorder + SpeechPlayer)          providers.py (Gemini Interactions + Groq fallback/STT/TTS)
api.js (same-origin fetch + keepalive)      models.py (Pydantic + validate_feedback grounding guards)
                                            prompts.py (ROLEPLAY_PROMPT, COACH_PROMPT)
                                            speech.py (200-char plain-text segmentation)
```

**Core architectural boundary:** Python is the single source of truth for conversation history, turn counts, stage transitions (`roleplay` -> `coach`), prompts, validation, and API keys. The browser never holds credentials, never mutates history directly, and only sends user actions (`create`, `answer`, `advance`, `finish`, `retry`, `stop`, `delete`) with UUID `requestId`s.

---

## 4. Backend Deep Dive (`server/`)

### 4.1 Launcher & Environment (`run.py`, `server/runtime.py`, `server/config.py`)
- **Launch paths:** `python3 run.py`, `.venv/bin/python -m server`, or `python3 server/app.py` (all enter `server.runtime.main()`).
- **Venv enforcement:** `server/runtime.py` checks `Path(sys.prefix).resolve() != (PROJECT_ROOT / ".venv").resolve()` and re-execs into `PROJECT_ROOT/.venv/bin/python` if needed.
- **Note on legacy doc paths:** `README.md` and some `docs/*.md` files mention `/home/bakar/Documents/NAVTTC/.venv`, which was an earlier path. The live code in `server/runtime.py` and `server/check_environment.py` uses `PROJECT_ROOT / ".venv"` (`/home/bakar/Documents/Internships/NETSOL/Voice_Coach/.venv`).
- **Config loading (`server/config.py`):** `load_settings()` parses only whitelisted `ENV_KEYS` without mutating `os.environ`. Precedence (lowest to highest):
  1. `PROJECT_ROOT.parents[2] / ".env"`
  2. `PROJECT_ROOT / ".env"`
  3. `os.environ`
- **Whitelisted `ENV_KEYS` & defaults:**
  - `GEMINI_API_KEY` (alias `GOOGLE_API_KEY`) — default `""`
  - `GROQ_API_KEY` — default `""` (used for Whisper STT, backup reasoning, and fallback TTS)
  - `GROQ_API_KEY2` (alias `GROQ_API_KEY_2`) — default `""` (preferred for Orpheus TTS only)
  - `GEMINI_MODEL` — default `"gemini-3.5-flash-lite"`
  - `GROQ_REASONING_MODEL` — default `"openai/gpt-oss-20b"`
  - `GROQ_STT_MODEL` — default `"whisper-large-v3-turbo"`
  - `GROQ_TTS_MODEL` — default `"canopylabs/orpheus-v1-english"`
  - `GROQ_TTS_VOICE` — default `"troy"`
  - `HOST` — default `"127.0.0.1"`
  - `PORT` — default `4317`
  - Fixed in `Settings`: `timeout_seconds = 30`, `retry_delay_seconds = 0.5`.

### 4.2 FastAPI App, Security Middleware & Cancellation (`server/app.py`)
- **`LocalMiddleware`:**
  - Rejects non-local `Host` headers (allows `localhost`, `127.0.0.1`, `::1`, `settings.host`; rejects userinfo) with `403 INVALID_ORIGIN`.
  - Rejects mismatched `Origin` headers and `sec-fetch-site: cross-site` with `403 INVALID_ORIGIN`.
  - Enforces body size limits on both `Content-Length` and chunked request streams (`64 KB` for JSON, `5 MB` for `/api/transcribe`), returning `413 PAYLOAD_TOO_LARGE`.
  - Sets security headers on every response: `cache-control: no-store`, `x-content-type-options: nosniff`, `referrer-policy: no-referrer`, `permissions-policy: microphone=(self), camera=()`, and strict CSP (`default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`).
- **`cancellable(request, coroutine)`:**
  - Races the provider task against a `0.03s` `request.is_disconnected()` watcher using an explicit `finished` `asyncio.Event` (prevents Starlette's disconnect probe from swallowing cancellations after fast responses).
  - Cancels the upstream HTTPX task immediately on client disconnect or `Stop`, returning `499 REQUEST_CANCELLED`.
- **Endpoints:**
  - `GET /api/config` — Prunes expired sessions; returns `mode`, `configured` (`gemini`, `groq`, `coaching`, `speech`), `scenario`, `defaultContext`, `maxAnswers: 3`, `maxRecordingSeconds: 60`.
  - `POST /api/practice` — Creates a `Practice` session (`StartRequest`: `requestId`, `context`).
  - `POST /api/practice/{session_id}/answer` — Records one learner answer (`AnswerRequest`: `requestId`, `text` 1..4000 chars).
  - `POST /api/practice/{session_id}/advance` — Runs `roleplay` or `coach` for the current `pending` stage (`cancellable`).
  - `POST /api/practice/{session_id}/finish` — Moves `pending` to `"coach"` (requires `>=1` accepted answer and no existing feedback).
  - `POST /api/practice/{session_id}/retry` — Appends a new `Attempt` with `pending = "roleplay"` using the same `Context` (max 10 attempts).
  - `POST /api/practice/{session_id}/stop` — Increments `generation`, cancels `inflight` task, preserves accepted answers.
  - `DELETE /api/practice/{session_id}` — Marks `deleted = True`, stops `inflight`, removes session (`204`).
  - `POST /api/speech/segments` — Splits `text` (1..4000 chars) into `<=200` char segments via `speech_segments()`.
  - `POST /api/speak` — Generates WAV bytes via Orpheus for `text` (`<=200` chars) (`cancellable`).
  - `POST /api/transcribe` — Accepts `audio/webm`, `audio/ogg`, `audio/mp4`, `audio/mpeg`, `audio/wav`, `audio/x-wav` (`>=64` bytes, `<=5 MB`), returns `{"text": ...}` (`cancellable`).

### 4.3 Session State & Idempotency (`server/sessions.py`)
- **`PracticeStore`:** In-memory store with `ttl_seconds=3600` (pruned on access) and `max_sessions=100` (`503 SESSION_LIMIT`).
- **`Practice`:** Holds `session_id` (`secrets.token_urlsafe(24)`), `context`, `attempts: list[Attempt]`, `pending: "roleplay" | "coach" | None`, `generation: int`, `lock: asyncio.Lock`, `inflight: asyncio.Task | None`, `requests: OrderedDict` (max 256 entries), `deleted: bool`.
- **Turn progression:**
  - New session starts with `pending = "roleplay"`.
  - `advance()` generates stakeholder opening -> `pending = None`, `playback = {"text": ..., "speaker": "Project manager"}`.
  - `answer()` appends `{"role": "user", "content": text}`; sets `pending = "coach"` if `answers >= MAX_ANSWERS (3)` else `"roleplay"`.
  - `finish()` (after `>=1` answer) sets `pending = "coach"`.
  - `advance()` on `"coach"` passes `previous = attempts[-2].messages` (if `len(attempts) > 1`) to `provider.coach()`, commits `attempt.feedback`, sets `playback = {"text": result.summary, "speaker": "Coach"}`.
- **Idempotency:** Every mutating action hashes `[operation, payload]` with SHA-256 against `requestId`. Replaying the same `requestId` + payload returns the current snapshot without duplicating turns; reusing a `requestId` for a different payload raises `409 REQUEST_CONFLICT`.
- **Stale-result guard:** If `Stop` or `Reset` runs while `advance()` is awaiting a provider, `generation` increments (or `deleted` becomes `True`), so any late provider return raises `409 STALE_REQUEST` without mutating `attempts`.

### 4.4 AI Providers & Fallback (`server/providers.py`)
- **`Providers.request()`:** 30s `asyncio.timeout` + `httpx.AsyncClient(follow_redirects=False)`. Retries once on `502`/`503`/`504` after `0.5s`. Redacts all configured keys and `gsk_*` / `AIza*` patterns before passing error details to `diagnostic`. Maps upstream errors to specific `AppError` codes (`MODEL_TERMS_REQUIRED`, `PROVIDER_ACCESS`, `PROVIDER_RATE_LIMIT`, `PROVIDER_MODEL`, `PROVIDER_BUSY`, `PROVIDER_TIMEOUT`, `PROVIDER_NETWORK`).
- **Gemini (`Providers.gemini()`):** `POST https://generativelanguage.googleapis.com/v1beta/interactions` with `Api-Revision: 2026-05-20`, `store: False`, `temperature: 0.4`, `max_output_tokens: 4096`, JSON `response_format` schema, and `thinking_level="low", thinking_summaries="none"` for `gemini-[34]*`.
- **Groq Backup Reasoning (`Providers.groq_reasoning()`):** `POST https://api.groq.com/openai/v1/chat/completions` with `response_format: {"type": "json_schema", "json_schema": {"name": "voice_coach", "strict": True, "schema": schema}}` and `reasoning_effort: "medium"`.
- **Fallback & Validation Retry (`Providers.reasoning()`):**
  - Tries Gemini + validator first.
  - On any `AppError` (if `fallback_enabled=True` and `groq_key` is set), logs `reasoning_fallback` and runs Groq with the exact same payload and validator. *Asyncio cancellation propagates without triggering fallback.*
  - If Groq output fails validation (`INVALID_PROVIDER_OUTPUT`), appends `SERVER VALIDATION: <hint>` to the system prompt and regenerates **at most once**. Rejected feedback is never committed.
- **Orpheus TTS (`Providers.speak()`):** Tries `groq_voice_key` (`GROQ_API_KEY2` / `GROQ_API_KEY_2`) first, then `groq_key` if the error is `MODEL_TERMS_REQUIRED`, `PROVIDER_ACCESS`, or `PROVIDER_RATE_LIMIT`. Validates `RIFF`/`WAVE` header (`len >= 44`).
- **Whisper STT (`Providers.transcribe()`):** Multipart upload with `language="en"` and domain `prompt`. Rejects blank transcripts (`422 EMPTY_TRANSCRIPT`) and >4000 chars (`422 ANSWER_TOO_LONG`).

### 4.5 Validation, Prompts & Speech (`server/models.py`, `server/prompts.py`, `server/speech.py`)
- **`RoleplayResponse` validation (`server/providers.py`):** Requires `reply.count("?") == 1`.
- **`validate_feedback()` (`server/models.py`):**
  1. **Evidence quotes:** Every `strength.quote` and `improvements[i].quote` must be a normalized contiguous substring of at least one `user` message in the **current** attempt.
  2. **First-attempt comparison:** `comparison` must be empty when `previous_history is None`.
  3. **Numeric grounding:** `improved_message` cannot introduce numbers (including `NUMBER_WORDS` `zero`..`ninety`) absent from `context.known_facts`.
  4. **Date grounding:** Weekday names and `in/by/before/after/on <Month>` across `feedback_claim_texts()` must appear in `context.known_facts` (avoids false-positives on modal `"may"`).
  5. **Relative schedule grounding:** `(this|next|following) (sprint|week|month|quarter|year|cycle|iteration|release)` across `feedback_claim_texts()` must appear in `known_facts` (except `"this release"` when `"release"` is in `known_facts`).
  6. **Duration-vs-delivery guard (`DELIVERY_TIMING_PATTERNS`):** Rejects turning work duration into a delivery date/window (e.g., `"will be ready in two working days"`), while allowing grounded approval phrasing (e.g., `"can be released after scope approval"`).
  7. **Unmeasured impact guard (`ZERO_IMPACT_PATTERNS`):** When `known_facts` states impact is unmeasured, rejects `"no customer impact"` / `"zero customer impact"` claims.
- **`speech_segments()` (`server/speech.py`):** Strips Markdown links, headings, emphasis, and list bullets, then splits at `. ` / `? ` / `! ` (if past midpoint) or space to keep every segment `<=200` chars.

---

## 5. Frontend Deep Dive (`web/`)

- **No-build ES modules:** `index.html` loads `/styles.css` and `<script type="module" src="/app.js"></script>`. Inline scripts/styles are blocked by CSP.
- **`PracticeSession` (`web/session.js`):**
  - States: `IDLE`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `SYNTHESIZING`, `SPEAKING`, `ERROR`.
  - **`startWithAnswer(context, text)`:** Typing in `#answer-text` and pressing `Enter` / `Send answer` before clicking `Start practice` automatically runs `create -> advance -> answer -> advance`.
  - **Barge-in:** Submitting a text answer during `SPEAKING` or `SYNTHESIZING` aborts audio playback and submits the answer.
  - **Non-blocking voice errors:** Failures during `speak` populate `this.voiceError` and render `#voice-notice` (`Retry audio`, `Turn voice off`, `×`) while returning `state` to `IDLE` so `#answer-text`, `#send-button`, `#record-button`, and `#starter-bar` remain usable.
  - **`stop()` vs `reset()`:** `stop()` increments `generation`, aborts fetch/audio/mic, and calls `POST /api/practice/{id}/stop` (keeping accepted turns; `Continue practice` resumes `pending`). `reset()` calls `DELETE /api/practice/{id}` once (single request, no competing `/stop`) and clears `snapshot` and `pending`.
- **`Recorder` & `SpeechPlayer` (`web/audio.js`):**
  - `Recorder` prefers `audio/webm;codecs=opus` -> `audio/webm` -> `audio/mp4` -> `audio/ogg;codecs=opus`, enforces 60s timer and 5 MB cap.
  - `SpeechPlayer` fetches segments via `POST /api/speech/segments`, fetches WAVs sequentially via `POST /api/speak`, revokes object URLs, waits `guardMs = 200` after playback ends before re-enabling mic, and surfaces `NotAllowedError` as `Tap to play reply` (`#play-button`).
- **UI Contract (`web/index.html`, `web/styles.css`, `tests/test_ui_contract.py`):**
  - `#how-button` must stay visible on mobile (`<=700px`).
  - Controls must maintain readable touch targets (`>=44px` `.icon-button`, `>=46px` `.button`), `16px` base font, and non-decorative button labels (no arrows/numbers).
  - `#familiarity` `<option>` values (`"Business-focused; prefers plain language"`, `"Some technical context; explain trade-offs"`) must match backend expectations while keeping short visible labels.

---

## 6. Test Suite & Verification Commands

Run all commands from `/home/bakar/Documents/Internships/NETSOL/Voice_Coach` using `.venv/bin/python`:

| Command | Purpose | Live API Calls? |
| --- | --- | --- |
| `.venv/bin/python -m server.check_environment --dev` | Inspect `.venv` packages (`fastapi`, `uvicorn`, `httpx`, `pydantic`, `requests`, `pytest`). Never installs anything. | No |
| `.venv/bin/python -m pytest -q` | Run all **97** unit, API, session, fallback, QA-regression, and UI-contract tests. | No (mocked transports) |
| `.venv/bin/python -m unittest discover -s tests -p smoke_runtime.py -v` | Start/stop real local Uvicorn servers across all 3 launch paths (`run.py`, `python -m server`, `server/app.py`) and verify `/`, `/api/config`, session create/delete. | No |
| `python3 run.py` | Start local server at `http://127.0.0.1:4317`. | Only on user interaction |
| `.venv/bin/python -m server.check_providers --diagnostic` | Live provider check (flags: `--voice-only`, `--text-only`, `--gemini-only`, `--groq-only`, `--list-gemini-models`, `--model MODEL_ID`, `--whisper-audio WAV`). | **Yes** |
| `.venv/bin/python -m server.check_website --audio PATH.wav` | Spin up temporary server and run full HTTP cycle against live Whisper/Gemini/Orpheus. | **Yes** |

### Test File Breakdown (`tests/`)
- `tests/test_api.py` — `/api/config` key redaction, Groq-only coaching readiness, origin/host validation, full FastAPI practice + retry cycle, Stop/disconnect cancellation, Starlette disconnect-probe race regression, upload limits.
- `tests/test_sessions.py` — `PracticeStore` turn progression, 3-answer auto-transition to coaching, `requestId` idempotency, failed follow-up recovery, Stop stale-result discard, 10-attempt isolation, TTL expiry & deep-copy isolation.
- `tests/test_providers.py` — Gemini Interactions adapter (`store=false`), `validate_feedback` grounding (quotes, `may` vs May, empty attempt-1 comparison, schedules, duration-vs-delivery, unmeasured impact), transient retry, `MODEL_TERMS_REQUIRED`, dual Groq key selection & redaction, Whisper multipart/blank handling, speech segmentation.
- `tests/test_reasoning_fallback.py` — Gemini->Groq fallback on HTTP/transport/output errors, no fallback on cancellation, single corrective retry on invalid backup output, grounded vs ungrounded schedules, primary recovery on next turn.
- `tests/test_qa_regressions.py` — `.env` precedence & quoted-comment parsing, chunked `413` body limit, `Host`/`Origin`/`sec-fetch-site` edge cases, MIME parameters, number-word grounding, `"this release"` vs `"next release"`, approval phrasing (`"can be released after scope approval"`), single-`DELETE` browser reset.
- `tests/test_ui_contract.py` — Mobile `#how-button` visibility, touch target sizes, no decorative arrows, `<select>` value/label contract, easy-start cues & starter-bar contract.
- `tests/smoke_runtime.py` — End-to-end launcher checks for all 3 entry points.

---

## 7. Engineering Guardrails for Agents

1. **Restart the server after Python edits:** A running `run.py` process holds old `server/` modules in memory until restarted.
2. **Never leak credentials:** Never print, log, or return `.env` keys to `web/` or error messages. Use `Providers` redaction patterns.
3. **Never weaken grounding guards without regression tests:** Any change to `server/models.py` (`validate_feedback`) or `server/prompts.py` must pass `test_providers.py`, `test_reasoning_fallback.py`, and `test_qa_regressions.py`, and must not turn work durations into delivery dates or unmeasured impact into zero impact.
4. **Keep `web/` dependency-free & CSP-compliant:** No inline JS/CSS, no external CDNs, no Node/npm tooling.
5. **Verify before reporting:** Run `.venv/bin/python -m pytest -q` (and `smoke_runtime.py` if touching startup/middleware) after your final edit.
