# DevBridge - Python architecture

19 November 2026 | FastAPI Phase 1 implementation

## Python application core

FastAPI serves the current HTML/CSS interface and the same-origin API. Python owns the release-update scenario, Gemini/Groq integrations, prompts, request validation, feedback checks, temporary sessions, attempt histories, answer counts and retry workflow.

Gemini uses the Interactions API with structured output and `store=false`. On a Gemini configuration, access, network, timeout, rate-limit or output-validation error, Python falls back to Groq `openai/gpt-oss-20b` through Chat Completions with a strict JSON schema. Both providers receive the same scenario/history and use the same Python output validators. A rejected backup response gets at most one corrective generation with a validation hint; an invalid result is never committed. Cancellation propagates without starting a fallback request.

Groq Whisper transcribes completed recordings. Groq Orpheus generates WAV speech. `GROQ_API_KEY` serves Whisper and backup reasoning; optional `GROQ_API_KEY2` is preferred for Orpheus alone. Provider keys are read on the server and never returned to the browser. All configured keys are redacted from diagnostic messages.

## Authoritative practice state

`PracticeStore` in `server/sessions.py` creates an opaque temporary session and keeps its context and attempts in process memory. A session starts with a pending stakeholder question. Accepted answers are recorded once; after the third answer, Python moves the session into coaching. Finish can request coaching after the first answer.

The browser cannot submit or overwrite conversation history. It sends an answer and a unique request identifier. Replaying that action does not duplicate the answer. Generated responses are committed once. Retry starts a separate attempt with the same context and passes the previous attempt to the coach for comparison.

Stop invalidates in-flight results, cancels provider work and preserves the current pending step for explicit recovery. Reset deletes the session. Disconnect cancellation and generation checks prevent stale results from being committed after Stop or Reset.

Sessions expire after one hour of inactivity. Expired sessions are pruned on access. The prototype caps concurrent sessions and retry attempts to keep memory bounded. There is no database, user account or durable session storage.

## API

| Endpoint | Purpose |
| --- | --- |
| GET /api/config | Key-presence and coaching/speech readiness booleans, initial scenario and default context; no credentials. |
| POST /api/practice | Create a temporary practice with validated context. |
| POST /api/practice/{id}/answer | Accept one learner answer idempotently. |
| POST /api/practice/{id}/advance | Generate the pending stakeholder question or coaching result. |
| POST /api/practice/{id}/finish | Queue coaching after at least one accepted answer. |
| POST /api/practice/{id}/retry | Start a new attempt with the same facts. |
| POST /api/practice/{id}/stop | Cancel in-flight work while retaining accepted turns. |
| DELETE /api/practice/{id} | Remove the temporary session. |
| POST /api/transcribe | Accept raw browser audio and return a Whisper transcript. |
| POST /api/speech/segments | Prepare ordered speech segments in Python. |
| POST /api/speak | Return one Groq WAV segment. |

## Necessary browser JavaScript

- `web/app.js`: DOM rendering, form controls and accessible status updates.
- `web/api.js`: same-origin fetch transport and abort signals.
- `web/audio.js`: microphone permission, MediaRecorder, HTML audio playback and audio-resource cleanup.
- `web/session.js`: coordinate browser I/O with the Python workflow; it does not generate questions, grade, store authoritative history or decide the next interview stage.

Speech sanitization and segmentation were moved from JavaScript to Python. The browser plays the returned segments sequentially and keeps recording inactive until the complete queue and acoustic guard finish. Audio that requires a user gesture exposes a Tap to Play control.

## Validation and limits

Pydantic bounds context, answer and provider-output sizes. Python requires one question in the stakeholder response, checks that feedback evidence appears in actual learner responses and rejects selected newly invented date, numeric or relative-schedule claims. These guards do not replace human review of meaning, uncertainty and authority. A work duration does not establish a scheduled delivery date.

Uploads are limited to 5 MB; browser recording stops at 60 seconds. Each provider HTTP request has an overall timeout and at most one retry for transient server errors. Fallback and one corrective generation can add latency. API failures preserve accepted answers for recovery. The disconnect watcher uses an explicit completion event so cleanup finishes even if Starlette consumes a cancellation in its disconnect probe. Cross-origin requests and untrusted Host headers are rejected on the local server.

The research PDF describes the product design at the documentation stage. See [the verification report](PHASE_1_VERIFICATION.md) for the current implementation and live-service status.
