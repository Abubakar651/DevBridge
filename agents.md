# agents.md — DevBridge (Voice Coach)

Comprehensive engineering, architecture, and workflow reference for AI coding agents working in `NETSOL/Voice_Coach`.

---

## 1. Product Purpose, Learning Objective & Scope

**DevBridge** (folder name `NETSOL/Voice_Coach` retained for local path compatibility) is a spoken workplace communication coach for **software developers** and **AI/ML engineers**.

- **Goal:** Help engineers explain technical work, reasoning, constraints, AI/ML limitations, and recommendations clearly, confidently, and respectfully to people with less technical context.
- **Confirmed coaching loop:**
  `Role-play the stakeholder -> Give grounded feedback -> Offer an improved explanation -> Practise again`
  Retries keep the exact same scenario facts (`Context`) and store each attempt separately for side-by-side comparison.
- **Target stakeholders (from [Voice_Coach_Project_Plan.pdf](output/pdf/Voice_Coach_Project_Plan.pdf) V3.0 — all implemented in Phase 2 / Jira `DEV-20`):**
  1. **VP of Operations** — AI/ML progress, business outcomes, rollout approval *(preset: `churn-pitch`)*.
  2. **Project manager** — delivery delays, dependencies, stability trade-offs, next steps *(preset: `two-day-delay`)*.
  3. **Client** — value, feasibility, scope changes, delivery options *(preset: `client-scope-change`)*.
  4. **IT manager** — operational impact, support needs, AI/ML evaluation limits & pilots *(presets: `it-ops-handoff`, `ai-ml-limits`)*.
  5. **HR representative** — personal contributions, responsibilities, workload, handover impact *(preset: `hr-contribution`)*.
- **5-dimension communication checklist (`Dimension` in `server/models.py`):**
  1. `Audience clarity` — plain language; necessary technical terms explained.
  2. `Structure and relevance` — outcome and business impact before unnecessary implementation detail.
  3. `Assertiveness` — clear position and recommendation; uncertainty stated when justified; polite requests and decision questions remain valid.
  4. `Respect` — avoids blame, dismissiveness, and assumptions about listener intelligence.
  5. `Accuracy and next steps` — facts and limits preserved; next action or needed decision is clear.
- **Superseded legacy scope:** Earlier OOP/SQL technical-interview drills, technical-depth grading, fixed 5-answer interviews, the old `release-update` PDF-export scenario, and the legacy Node/npm backend are superseded. `build_voice_coach_board.py`, `miro_client.py`, and `outputs/board_manifest.json` remain only as historical Miro planning utilities.
- **Project plan reference:** [Voice_Coach_Project_Plan.pdf](output/pdf/Voice_Coach_Project_Plan.pdf) (V3.0, generated from `docs/voice_coach_documentation.json`).

---

## 2. Current Implementation Status vs. Roadmap

### Currently Implemented (Phases 1, 2, 3 & 4 — Full Roadmap Complete)
- **Composable personas, difficulty & mix-and-match (`server/scenario.py`, `web/app.js`):**
  - **5 stakeholder personas (`PERSONAS`):** `vp-ops`, `project-manager`, `client`, `it-manager`, `hr-representative`, each defining `priorities`, `noticesFirst`, `evidenceBar`, `openingStyle`, `pushbackTriggers`, and `coachingFocus`.
  - **3 stakeholder pressure / difficulty levels (`DIFFICULTIES`, Phase 3 / `DEV-32`):** `supportive` (*Supportive · warm & guiding*), `standard` (*Standard · realistic check-in*), and `skeptical` (*Skeptical · high-scrutiny pushback*), injected into `ROLEPLAY_PROMPT` and `COACH_PROMPT` and selectable via `#difficulty` in **Set the scene**.
  - **5-dimension checklist metadata & attempt comparison matrix (`CHECKLIST_DIMENSIONS`, Phase 3 / `DEV-32`, `DEV-34`):** `#comparison` renders a 5-signal checklist grid (`#checklist-comparison`) comparing `Attempt N-1` and `Attempt N` across `Audience clarity`, `Structure and relevance`, `Assertiveness`, `Respect`, and `Accuracy and next steps` (`Improved ✓`, `Strong ✓`, `Focus next`, `Practising now`), paired with `#use-example-button` (*Retry with example draft*).
  - **6 selectable scenarios (`SCENARIOS`):** `churn-pitch` (`vp-ops`, AI/ML engineer), `two-day-delay` (`project-manager`, Software developer), `client-scope-change` (`client`, Software developer), `it-ops-handoff` (`it-manager`, Software developer), `ai-ml-limits` (`it-manager`, AI/ML engineer), and `hr-contribution` (`hr-representative`, Software developer).
  - **Independent mix-and-match & familiarity (`FAMILIARITY_OPTIONS`):** Learners can choose a preset and independently swap `#persona`, `#difficulty`, `#discipline` (`AI/ML engineer` / `Software developer`), and `#familiarity` (**Plain language, business focused**, **Some technical context**, **Technical lead (architecture ok)**) without overwriting custom `knownFacts` or `goal`, displaying a `Custom mix` or `Customized` badge (`#scenario-custom-badge`).
- **Mobile PWA, offline shell & shared-demo controls (`Phase 4` / `DEV-36`, `DEV-37`–`DEV-40`):**
  - **Installable PWA (`web/manifest.webmanifest`, `web/icon-maskable.svg`, `web/sw.js`):** Standalone display metadata paired with a static-shell-only service worker (`devbridge-shell-v1`) that strictly excludes all `/api/*` and external requests.
  - **Offline banner & recovery (`web/app.js`):** Detects `online`/`offline` state to show `#offline-notice` (*Reconnect* button) and safely disable cloud actions until connectivity returns.
  - **Server access & usage limits (`server/config.py`, `server/app.py`):** Supports optional `ALLOWED_HOSTS`, HTTPS `X-Forwarded-Proto: https` with `Strict-Transport-Security`, constant-time `DEMO_ACCESS_TOKEN` verification (`401 ACCESS_REQUIRED`), and per-IP 60s sliding-window `RATE_LIMIT_PER_MINUTE` enforcement (`429 RATE_LIMITED`).
- **Turn budget & natural closing:** Up to **`MAX_ANSWERS = 10`** learner answers per attempt (`server/models.py`). When the learner finishes early or the stakeholder sets `RoleplayResponse.closed = True` after a learner answer, Python automatically queues `"coach"`.
- **Backend (`server/`):** Python 3.12 + FastAPI + Uvicorn + HTTPX + Pydantic. Owns personas, difficulties, checklist dimensions, scenarios, prompts, provider calls, structured-output validation, meaning-preservation guards, in-memory sessions, attempt histories, idempotency, rate limiting/access control, and speech segmentation.
- **Frontend (`web/`):** Plain HTML, CSS (Apple HIG / Liquid Glass design system with `auto` / `light` / `dark` themes, unsticky mobile header `<=700px`), and browser ES modules. No Node runtime, no npm, no bundler.
- **Voice & reasoning pipeline:**
  1. **Capture & Web Audio VAD (`web/audio.js`, `web/session.js`, Phase 3 / `DEV-33`):** Browser `MediaRecorder` (`Record answer` / `Done speaking`, 60s / 5 MB limit) enhanced with Web Audio `AudioContext` + `AnalyserNode` voice-activity and post-speech silence detection (`#auto-silence` *Auto-send on pause* toggle + live `#mic-status` indicator) while retaining manual controls and recovering transcribed text (`lastTranscribedText`) on downstream errors, plus always-open composer dock (`#answer-text`) + quick starter chips (`#starter-bar` with dynamic `starterLabels`).
  2. **Transcribe (`POST /api/transcribe`):** Groq Whisper (`whisper-large-v3-turbo`).
  3. **Reason (`POST /api/practice/{id}/advance`):** 3-stage fallback chain:
     **Gemini (`gemini-3.5-flash-lite`, Interactions API, `store=false`) -> Groq (`openai/gpt-oss-20b`, Chat Completions strict schema) -> OpenRouter (`openai/gpt-oss-20b`, Chat Completions strict schema + `require_parameters: true`)**.
     Cancellation (`asyncio.CancelledError`) never triggers fallback.
  4. **Speak (`POST /api/speech/segments` + `POST /api/speak`):** Groq Orpheus (`canopylabs/orpheus-v1-english`, voice `troy`, 200-char segment limit, WAV output). Includes a single bounded `429` burst retry on `speak()`, preserves real `429` errors if the secondary key lacks terms, and degrades non-blockingly in the UI (`#voice-notice`).
     *Deferred backlog task (**DEV-5** / **GH #5**):* Replace Groq Orpheus TTS with open-source `kokoro-onnx` / OpenRouter `hexgrad/kokoro-82m` / `piper-tts`.

### Deferred Backlog
- All planned Phases 1–4 from `Voice_Coach_Project_Plan.pdf` are implemented. The only remaining backlog item is **DEV-5** (*Replace Groq Orpheus TTS with open-source Kokoro-82M / Piper*).

---

## 3. Architecture & Data Flow

```text
Browser (web/)                              Python Server (server/)
──────────────                              ───────────────────────
index.html + styles.css (Liquid Glass)      run.py / server/runtime.py (../.venv)
app.js (DOM, theme, Brief/Edit, starters)   app.py (FastAPI + LocalMiddleware + cancellable)
session.js (UI state machine)      <─HTTP─> sessions.py (PracticeStore, Attempt, Lock, generation)
audio.js (Recorder + SpeechPlayer)          providers.py (Gemini -> Groq -> OpenRouter, Whisper, Orpheus)
api.js (same-origin fetch + keepalive)      models.py (Pydantic + validate_feedback grounding guards)
                                            prompts.py (ROLEPLAY_PROMPT, COACH_PROMPT)
                                            speech.py (200-char plain-text segmentation)
                                            scenario.py (PERSONAS, FAMILIARITY_OPTIONS, SCENARIOS, resolve_persona)
```

**Core architectural boundary:** Python is the single source of truth for conversation history, turn counts, stage transitions (`roleplay` -> `coach`), prompts, validation, and API keys. The browser never holds credentials, never mutates history directly, and only sends user actions (`create`, `answer`, `advance`, `finish`, `retry`, `stop`, `delete`) with UUID `requestId`s.

---

## 4. Backend Deep Dive (`server/`)

### 4.1 Launcher & Environment (`run.py`, `server/runtime.py`, `server/config.py`)
- **Shared virtual environment:** Lives one level up at `/home/bakar/Documents/Internships/NETSOL/.venv` (`PROJECT_ROOT.parent / ".venv"` in `server/runtime.py`, `parents[2] / ".venv"` in `server/check_environment.py`).
- **Launch paths:** `python3 run.py`, `../.venv/bin/python -m server`, or `python3 server/app.py` (all enter `server.runtime.main()`, which re-execs into `SHARED_VENV / "bin" / "python"` if launched from another Python).
- **Config loading (`server/config.py`):** `load_settings()` parses only whitelisted `ENV_KEYS` without mutating `os.environ`, strips whitespace on quoted/unquoted values, ignores whitespace-only overrides, validates `0 <= port <= 65535` (raising normalized `ValueError("PORT must be a valid port number.")` on non-numeric `PORT`), and checks `.env` in lowest-to-highest order:
  1. `PROJECT_ROOT.parents[2] / ".env"` (if `len(parents) > 2`)
  2. `PROJECT_ROOT.parents[1] / ".env"` (if `len(parents) > 1`)
  3. `PROJECT_ROOT / ".env"`
  4. `os.environ` / explicit `environment` mapping
- **Whitelisted `ENV_KEYS` & defaults:**
  - `GEMINI_API_KEY` (alias `GOOGLE_API_KEY`) — `""`
  - `GROQ_API_KEY` — `""` (Whisper STT, Groq backup reasoning, fallback TTS)
  - `GROQ_API_KEY2` (alias `GROQ_API_KEY_2`) — `""` (preferred for Orpheus TTS only)
  - `OPENROUTER_API_KEY` — `""` (secondary reasoning fallback)
  - `GEMINI_MODEL` — `"gemini-3.5-flash-lite"`
  - `GROQ_REASONING_MODEL` — `"openai/gpt-oss-20b"`
  - `OPENROUTER_MODEL` — `"openai/gpt-oss-20b"`
  - `GROQ_STT_MODEL` — `"whisper-large-v3-turbo"`
  - `GROQ_TTS_MODEL` — `"canopylabs/orpheus-v1-english"`
  - `GROQ_TTS_VOICE` — `"troy"`
  - `HOST` — `"127.0.0.1"`
  - `PORT` — `4317`
  - Fixed in `Settings`: `timeout_seconds = 30`, `retry_delay_seconds = 0.5`.

### 4.2 FastAPI App, Security Middleware & Cancellation (`server/app.py`)
- **`LocalMiddleware`:**
  - Calls `settings_loader()` inside `try/except`, returning `500 CONFIGURATION_ERROR` JSON on `ValueError` instead of crashing ASGI.
  - Rejects non-local `Host` headers (allows `localhost`, `127.0.0.1`, `::1`, `settings.host`; rejects userinfo), mismatched `Origin`, and `sec-fetch-site: cross-site` with `403 INVALID_ORIGIN`.
  - Rejects negative `Content-Length` (`400 INVALID_INPUT`) and enforces `64 KB` (JSON) / `5 MB` (`/api/transcribe`) limits across both `Content-Length` and chunked request bodies (`413 PAYLOAD_TOO_LARGE`).
  - Sets security headers on every response: `cache-control: no-store`, `x-content-type-options: nosniff`, `referrer-policy: no-referrer`, `permissions-policy: microphone=(self), camera=()`, and strict CSP (`default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`).
- **Exception handlers:** Standardized JSON `{"error": {"code", "message"}}` envelopes for `AppError`, `RequestValidationError` (`400`), `StarletteHTTPException` (`404 NOT_FOUND`, `405 METHOD_NOT_ALLOWED`), and unexpected `Exception` (`500 INTERNAL_ERROR` without traceback leakage).
- **`cancellable(request, coroutine)`:** Races the provider task against a `0.03s` `request.is_disconnected()` watcher using an explicit `finished` `asyncio.Event` (prevents Starlette's disconnect probe from swallowing cancellations). Cancels upstream HTTPX work immediately on disconnect/Stop (`499 REQUEST_CANCELLED`).
- **Endpoints:**
  - `GET /api/config` — Prunes expired sessions; returns `mode`, `configured` (`gemini`, `groq`, `coaching`, `speech` where `coaching` checks `gemini_key or groq_key or openrouter_key`), `scenario`, `scenarios` (`SCENARIOS`), `personas` (`PERSONA_LIST`), `familiarityOptions` (`FAMILIARITY_OPTIONS`), `defaultContext`, `maxAnswers` (`MAX_ANSWERS`), `maxRecordingSeconds: 60`.
  - `POST /api/practice` — Creates a `Practice` session (`StartRequest`).
  - `POST /api/practice/{session_id}/answer` — Records one learner answer idempotently (`AnswerRequest`, 1..4000 chars).
  - `POST /api/practice/{session_id}/advance` — Generates stakeholder reply or coaching feedback (`cancellable`).
  - `POST /api/practice/{session_id}/finish` — Moves `pending` to `"coach"` after `>=1` answer.
  - `POST /api/practice/{session_id}/retry` — Appends a fresh `Attempt` (`pending = "roleplay"`) with the same `Context` (max 10 attempts).
  - `POST /api/practice/{session_id}/stop` — Increments `generation`, cancels `inflight`, refreshes `touched`, preserves accepted turns.
  - `DELETE /api/practice/{session_id}` — Atomically pops session, cancels `inflight`, prunes (`204`).
  - `POST /api/speech/segments` — Splits `text` (1..4000 chars) into `<=200`-char segments via `speech_segments()`.
  - `POST /api/speak` — Generates WAV bytes via Orpheus for `text` (`<=200` chars) (`cancellable`).
  - `POST /api/transcribe` — Accepts `audio/webm`, `audio/ogg`, `audio/mp4`, `audio/mpeg`, `audio/wav`, `audio/x-wav` (`>=64` bytes, `<=5 MB`), returns `{"text": ...}` (`cancellable`).

### 4.3 Session State & Idempotency (`server/sessions.py`)
- **`PracticeStore`:** In-memory store (`ttl_seconds=3600`, `max_sessions=100`, `MAX_ANSWERS=10`, max 10 attempts/session).
- **Turn progression & natural closing:**
  - New sessions start with `pending = "roleplay"`.
  - `advance()` on `"roleplay"` resolves active speaker via `resolve_persona(practice.context.scenario_id, practice.context.persona_id)["label"]`, stores the assistant turn + `playback`, and checks `provider.last_roleplay_closed`: if `True`, sets `pending = "coach"` (auto-triggering coaching); otherwise `pending = None`.
  - `snapshot()` and `create()` use `model_dump(by_alias=True, exclude_none=True)` so omitting optional `personaId` keeps `snapshot["context"]` backward-compatible.
  - `answer()` appends the user turn and sets `pending = "coach"` if `answers >= MAX_ANSWERS (10)` else `"roleplay"`.
  - `advance()` refreshes `practice.touched = self.clock()` on completion.
- **Cancellation & races:** Shared `_cancel_inflight()` helper increments `generation` and cancels/awaits `inflight`. `delete()` pops the session atomically before cancelling so TTL expiry cannot raise `404` during `DELETE`. `stop()` raises `404` if deleted concurrently while awaiting cancellation.
- **Idempotency:** Hashes `[operation, payload]` with SHA-256 against `requestId` (max 256 remembered per session); payload mismatch raises `409 REQUEST_CONFLICT`.

### 4.4 AI Providers & Fallback (`server/providers.py`)
- **`Providers.request()`:** 30s `asyncio.timeout`, `follow_redirects=False`, 1 retry on `502`/`503`/`504` (and `429` only when `retry_on_429=True` for `speak()`, bounded `<= 2.0s` via `Retry-After` or `retry_delay_seconds`). Redacts `gemini_key`, `groq_key`, `groq_voice_key`, `openrouter_key`, and `gsk_*` / `AIza*` / `sk-or-v1-*` tokens in diagnostics. Maps `402` -> `PROVIDER_QUOTA`, `401`/`403` -> `PROVIDER_ACCESS`, `429` -> `PROVIDER_RATE_LIMIT`, `404` -> `PROVIDER_MODEL`, `503` -> `PROVIDER_BUSY`, `model_terms_required` -> `503 MODEL_TERMS_REQUIRED`.
- **Reasoning chain (`Gemini -> Groq -> OpenRouter`):**
  - `gemini()`: Calls `v1beta/interactions` (`Api-Revision: 2026-05-20`, `store: False`, `thinking_level="low"` for `gemini-[34]*`).
  - `_chat_completion_reasoning()` + `_run_backup_with_retry()`: Shared between `groq_reasoning()` and `openrouter_reasoning()` (`provider: {"require_parameters": True}`). Uses `strict: True` JSON schema and `_parse_json_output()` (strips optional Markdown code fences). Retries at most once with `SERVER VALIDATION: <hint>` on `INVALID_PROVIDER_OUTPUT`.
  - `roleplay()` & `coach()` resolve the active persona via `resolve_persona(context.scenario_id, context.persona_id)` and inject crisp behavioral fields (`priorities`, `noticesFirst`, `evidenceBar`, `openingStyle`, `pushbackTriggers` / `coachingFocus`) alongside `context` (`exclude_none=True`). `roleplay()` sets `self.last_roleplay_closed` and enforces `reply.count("?") == (0 if closed else 1)` (ignoring `closed=True` if `history` is empty).
- **Orpheus TTS (`speak()`):** Tries `groq_voice_key` then `groq_key` (`retry_on_429=True`), preserves an initial `429 PROVIDER_RATE_LIMIT` if fallback fails with `MODEL_TERMS_REQUIRED`/`PROVIDER_ACCESS`, and validates `RIFF`/`WAVE` header (`len >= 44`).
- **Whisper STT (`transcribe()`):** Normalizes MIME parameters (`mime_type.split(";")[0].lower().strip()`) via `AUDIO_EXTENSIONS` (`415 UNSUPPORTED_AUDIO` if unknown), uses broadened workplace/IT/AI/HR domain hints, and rejects blank transcripts (`422 EMPTY_TRANSCRIPT`) and >4000 chars (`422 ANSWER_TOO_LONG`).

### 4.5 Validation, Prompts & Speech (`server/models.py`, `server/prompts.py`, `server/speech.py`)
- **Dynamic context validation (`server/models.py`):** `Context.scenario_id` validates dynamically against `SCENARIO_BY_ID`, and optional `Context.persona_id` (`personaId`) validates against `PERSONA_BY_ID`.
- **`validate_feedback()` (`server/models.py`):**
  1. **Typography normalization (`_TYPOGRAPHIC_TRANSLATION`):** Normalizes curly single/double quotes, apostrophes, Unicode hyphens (`\u2010`, `\u2011`), and zero-width characters (`normalize_punctuation()` / `normalize()`).
  2. **Evidence quotes:** Every `strength.quote` and `improvements[i].quote` must contain at least one alphanumeric character and be a normalized contiguous substring of a current-attempt `user` turn.
  3. **First-attempt comparison:** `comparison` must be empty when `not previous_history` (and leading/trailing whitespace is trimmed).
  4. **Numeric grounding (`normalize_number_words()`):** Handles comma-grouped thousands, English number words (`zero`..`ninety`), compound tens (`twenty-five`), multipliers (`hundred`, `thousand`, `million`, `billion`), and `per cent` phrases across `improved_message` vs `known_facts`.
  5. **Date grounding (`_extract_dates()`):** Extracts weekdays, relative weekdays (`next Friday`), `Month Day` / `Day Month`, `Month Year`, ISO `YYYY-MM-DD`, unambiguous months, capitalized/prepositional `March` and `May` (avoiding modal `"may"`), and abbreviated months (`Jan`..`Dec`) across all `feedback_claim_texts()`.
  6. **Schedule, duration, impact, savings & AI limits guards:** `_RELATIVE_SCHEDULE_PATTERN` checks `this`/`next`/`following`/`upcoming`/`future`/`subsequent` schedules; `DELIVERY_TIMING_PATTERNS` rejects turning work duration into a delivery date/window; `ZERO_IMPACT_PATTERNS` rejects asserting zero impact when unmeasured; `FALSE_SAVINGS_PATTERNS` preserves unmeasured time/revenue/retention/cost savings; and `FALSE_LIVE_AI_PATTERNS` + `_has_affirmative_match()` stops claiming unestablished live AI accuracy is proven or production-ready without rejecting valid negated uncertainty.
- **`ROLEPLAY_PROMPT` & `COACH_PROMPT` (`server/prompts.py`):** Static prefix-cache-friendly system prompts that condition openings, follow-ups, pushback, and coaching focus on the supplied `persona` spec (`openingStyle`, `noticesFirst`, `priorities`, `evidenceBar`, `pushbackTriggers`, `coachingFocus`), require verbatim current-attempt user quotes, forbid invented schedules/dates/metrics across all fields, and enforce exact `""` for `comparison` on first attempts.
- **`speech_segments()` (`server/speech.py`):** Strips Markdown links (including parentheses in URLs), headings, blockquotes, list markers, strikethrough, code backticks, and outer emphasis underscores (preserving `snake_case`), splitting cleanly on sentence/word boundaries within `window = remaining[: limit + 1]`.

---

## 5. Frontend Deep Dive (`web/`)

- **No-build ES modules & Apple HIG styling:** `web/index.html` loads `/styles.css` (Apple Liquid Glass light/dark tokens via `data-theme="auto|light|dark"`, persisted in `localStorage` under `devbridge-theme`) and `<script type="module" src="/app.js">`. Inline scripts/styles are blocked by CSP.
- **Workspace layout (`web/index.html`, `web/app.js`):**
  - Loads centered on **The conversation** (`data-scene-open="false"`, `data-coach-open="false"`), with `#scene-toggle` (**Set the scene**) and `#coach-toggle` (**Your coaching notes**, auto-opens when feedback arrives and shows a `Ready` badge).
  - `#context-panel` includes a **Brief / Customize** segmented switcher (`#brief-mode-brief`, `#brief-mode-edit`), scenario selector (`#scenario`: all 6 Phase 2 presets), **Stakeholder persona** selector (`#persona`: all 5 personas), **Your role** (`#discipline`), **Audience prefers** (`#familiarity`: 3 levels including `Technical lead (architecture ok)`), dynamic header pill (`#header-scenario-pill`), 10-step progress bar (`#turn-steps`), inline error banners (`#facts-error`, `#goal-error`), and dynamic stakeholder labels from `selectedPersona()` / `syncPersonaUI()`. Swapping `#persona`, `#discipline`, or `#familiarity` preserves edited `#facts`/`#goal`, while changing `#scenario` updates both `dataset.starter` and visible chip labels via `starterLabels`; `#how-dialog` uses persona-neutral `"simulated stakeholder"` wording, and `readContext()` includes `personaId`.
- **`web/api.js`:** `sessionPath()` validates/encodes `sessionId`; `request()` catches fetch failures as `NETWORK_ERROR`, non-JSON bodies as `INVALID_RESPONSE`, uses `keepalive: true` for `stop`/`reset`, and validates `segments` array responses.
- **`web/audio.js`:**
  - `Recorder`: Probes 8 `AUDIO_MIME_PRESETS`, falls back safely in `_createRecorder()`, enforces 60s / 5 MB limits, guards `finish()` against `InvalidStateError` (`state === 'inactive'`) and double-settlement (`settled`), and cleans streams/listeners via `_cleanupRecorder()`.
  - `SpeechPlayer`: Stops any prior playback on `play()`, runs segments sequentially via `/api/speech/segments` + `/api/speak`, wraps `audio.play()` safely, waits `guardMs = 200` after playback, and surfaces `NotAllowedError` as `Tap to play reply`.
- **`web/session.js`:**
  - `PracticeSession` states: `IDLE`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `SYNTHESIZING`, `SPEAKING`, `ERROR`.
  - `_stopSpeech()` aborts playback/speech requests locally without hitting server `/stop` when muting or barging in by typing.
  - Preserves `queuedAnswer` if `create` succeeds and `advance` fails (clearing `queuedAnswer` and `pending` only on `NON_RETRYABLE_CODES`), and auto-chains `advance` to `"coach"` when `snapshot.pendingStage === 'coach'` after playback (`stage.nextStage === 'coach'`).
  - `reset()` sends a single `DELETE /api/practice/{id}` without a competing `/stop`.

---

## 6. Environment, Commands & Verification

Run all commands from `/home/bakar/Documents/Internships/NETSOL/Voice_Coach` using the shared parent venv `/home/bakar/Documents/Internships/NETSOL/.venv/bin/python`:

| Command | Purpose | Live API Calls? |
| --- | --- | --- |
| `../.venv/bin/python -m server.check_environment --dev` | Inspect `NETSOL/.venv` packages (`fastapi`, `uvicorn`, `httpx`, `pydantic`, `requests`, `pytest`). Never installs anything. | No |
| `../.venv/bin/python -m pytest -q` | Run all **158** unit, API, session, fallback, persona/scenario, QA-regression, and UI-contract tests. | No (mocked transports) |
| `../.venv/bin/python -m unittest discover -s tests -p smoke_runtime.py -v` | Start/stop real local Uvicorn servers across all 3 launch paths (`run.py`, `python -m server`, `server/app.py`) and verify `/`, `/api/config`, session create/delete. | No |
| `python3 run.py` | Start local server at `http://127.0.0.1:4317` (auto-re-execs into `NETSOL/.venv`). | Only on user interaction |
| `../.venv/bin/python -m server.check_providers --diagnostic` | Live provider check (`--voice-only`, `--text-only`, `--gemini-only`, `--groq-only`, `--openrouter-only`, `--list-gemini-models`, `--model MODEL_ID`, `--whisper-audio WAV`). | **Yes** |
| `../.venv/bin/python -m server.check_website --audio PATH.wav` | Spin up temporary server and run full HTTP cycle against live providers. | **Yes** |

### Test Suite Breakdown (`tests/`)
- `tests/test_api.py` — `/api/config` readiness & redaction (Groq-only, OpenRouter-only), origin/host checks, full FastAPI cycle & retry, Stop/disconnect cancellation, disconnect-probe race, upload/speech limits.
- `tests/test_sessions.py` — `PracticeStore` turn progression, auto-coaching on `MAX_ANSWERS` or natural closing, `requestId` idempotency, failed follow-up recovery, Stop stale-result discard, `delete()` TTL-race & concurrency safety, 10-attempt isolation.
- `tests/test_providers.py` — Gemini Interactions adapter (`store=false`), `validate_feedback` grounding, transient/429 Orpheus retry & non-masking fallback, `MODEL_TERMS_REQUIRED`, dual Groq key selection & `sk-or-v1-*`/key redaction, `402` `PROVIDER_QUOTA`, Whisper MIME normalization, speech segmentation.
- `tests/test_reasoning_fallback.py` — `Gemini -> Groq -> OpenRouter` fallback matrix, `require_parameters: True`, no fallback on cancellation, single corrective validation retry, grounded vs ungrounded schedules.
- `tests/test_qa_regressions.py` — `.env` precedence/trimming/`PORT` errors, middleware/HTTP/unhandled JSON error envelopes, chunked `413` limit, curly quotes, advanced date/number-word grounding, schedule & delivery-timing guards, natural closing, single-`DELETE` reset.
- `tests/test_ui_contract.py` — Mobile `#how-button` visibility, touch target sizes (`>=44px` `.icon-button`, `>=46px` `.button`), no decorative arrows, `<select>` value/label contract, easy-start cues & starter-bar contract.
- `tests/test_personas_slice1.py` — 5-persona registry & `FAMILIARITY_OPTIONS`, `/api/config` exposure, dynamic `scenarioId`/`personaId` validation & `400` rejections, mix-and-match `it-manager` flow, unmeasured savings & unestablished live AI guards.
- `tests/test_ui_slice2.py` — `#persona` selector, 3rd familiarity option, persona-neutral `#how-dialog`, non-destructive `web/app.js` persona wiring, dynamic `starterLabels`.
- `tests/test_scenarios_slice3.py` — `client-scope-change` & `it-ops-handoff` registration, end-to-end persona cycles, duration & impact guards, `/api/config` order.
- `tests/test_scenarios_slice4.py` — All 6 Phase 2 scenarios covering all 5 personas, `ai-ml-limits` & `hr-contribution` cycles + retries, AI/HR grounding guards, `/api/config` counts.
- `tests/test_ui_ux_polish.py` — Discoverable scene triggers (`DEV-26`), coaching drawer auto-collapse (`DEV-27`), `Custom mix`/`Customized` badge (`DEV-28`), early-finish `COACH_PROMPT` & `Recorder.cancel()` fix (`DEV-29`), unsticky mobile header & stakeholder prose casing (`DEV-30`).
- `tests/test_phase3_slice1.py` — Stakeholder difficulty levels (`DIFFICULTIES`), `CHECKLIST_DIMENSIONS`, `/api/config` exposure, `Context.difficulty` validation, and provider payload flow (`DEV-32`).
- `tests/test_phase3_slice2.py` — Web Audio VAD pre-speech silence immunity, post-speech pause auto-finish, manual-only mode (`setAutoStopSilence(false)`), and `AudioContext` cleanup (`DEV-33`).
- `tests/test_phase3_slice3.py` — `#difficulty`, `#auto-silence`, `#use-example-button`, and 5-signal `#checklist-comparison` matrix contract tests (`DEV-34`).
- `tests/test_phase3_slice4.py` — 10-cycle VAD silence/retry/stop/reset durability test, multi-attempt checklist comparison flow, and `docs/PHASE_3_PILOT_VALIDATION.md` verification (`DEV-35`).
- `tests/test_phase4_slice1.py` — PWA `manifest.webmanifest`, maskable icon, and static-shell-only `/sw.js` caching contract (`DEV-37`).
- `tests/test_phase4_slice2.py` — Offline banner `#offline-notice`, `#offline-retry-button`, `online`/`offline` recovery, and `/sw.js` registration contract (`DEV-38`).
- `tests/test_phase4_slice3.py` — `ALLOWED_HOSTS`, HTTPS HSTS header, optional `DEMO_ACCESS_TOKEN` auth guard, and sliding-window `RATE_LIMIT_PER_MINUTE` checks (`DEV-39`).
- `tests/test_phase4_slice4.py` — Full Phase 4 completion gate end-to-end cycles (`ai-ml-limits` + `hr-contribution` with Retry) and `docs/PHASE_4_PWA_VALIDATION.md` verification (`DEV-40`).
- `tests/smoke_runtime.py` — End-to-end launcher checks for all 3 entry points.

---

## 7. Engineering Guardrails for Agents

1. **GitHub & Jira workflow:** Track changes in Jira project `DEV` (`Devbridge`, grouped by `Workstream -> Task`, e.g., **DEV-20** for Phase 2, **DEV-25** for UI/UX Polish, **DEV-31** for Phase 3, and **DEV-36** for Phase 4) and GitHub `Abubakar651/DevBridge` incrementally one task/slice at a time; never bulk-create tasks unless asked. Deferred open backlog item: **DEV-5** / **GH #5** (Orpheus TTS replacement).
2. **Restart the server after Python edits:** A running `run.py` process holds old `server/` modules in memory until restarted.
3. **Never leak credentials:** Never read, print, log, or commit `.env` values or return keys to `web/`.
4. **Never weaken grounding or UI contracts:** Keep `validate_feedback()` guards (`server/models.py`), `RoleplayResponse` question-count rules (`server/providers.py`), and `test_ui_contract.py` invariants passing.
5. **Keep `web/` dependency-free & CSP-compliant:** No inline JS/CSS, no external CDNs, no Node/npm tooling.
6. **Verify after edits:** Run `../.venv/bin/python -m pytest -q` and `../.venv/bin/python -m unittest discover -s tests -p smoke_runtime.py -v` after your final edit.
