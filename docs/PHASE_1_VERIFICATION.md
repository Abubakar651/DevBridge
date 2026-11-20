# DevBridge Phase 1 verification - Python / FastAPI

Date: 19 November 2026 (Asia/Karachi)

After the independent QA remediation, **95 automated tests pass with no expected failures**, and all three Python launch modes pass. A post-fix live HTTP run verified the page resources, Whisper input, Gemini role-play and coaching, grounded evidence, retry isolation and reset. Orpheus also completed a separate live speech-to-transcription round trip through the new credential fallback. Current browser rendering, physical-device behavior and human communication-quality acceptance remain separate, as detailed below.

[Post-fix live results](PHASE_1_POST_FIX_CHECK.json) | [Earlier complete live run](PHASE_1_LIVE_CHECK.json) | [Run guide](../README.md)

## Implementation boundary

The Node backend, npm package manifest, JavaScript provider-check script and JavaScript backend tests have been removed. Python owns the application workflow, scenarios, prompts, providers, validation, histories, attempt counting, retries, idempotency and speech segmentation.

JavaScript remains in `web/` for browser recording/playback, same-origin requests and interface updates. No Node runtime or npm installation is required to start the application.

## Virtual environment checked before further installation

The application uses `/home/bakar/Documents/NAVTTC/.venv/bin/python` (Python 3.12). The nested `Internships/NETSOL/Voice_Coach/.venv` remains removed. All runtime dependencies were checked and already installed. Pytest was checked, found missing, and installed with its missing test dependencies (`iniconfig` and `pluggy`) to run the existing regression suite. No runtime packages were added.

| Package | Installed version |
| --- | --- |
| fastapi | 0.164.0 |
| uvicorn | 0.53.0 |
| httpx | 0.28.1 |
| pydantic | 2.14.1 |
| requests | 2.34.2 |
| pytest (test tooling) | 9.2.0 |

From the project folder, run `/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_environment` to repeat this inspection. Add `--dev` to include optional pytest tooling. The command only reports package presence and versions.

## Latest shared-environment checks

- **95 Python tests passed** in the shared environment with `/home/bakar/Documents/NAVTTC/.venv/bin/python -m pytest -q`.
- Tests cover Gemini success, access/model/rate-limit/server/network/timeout failures, Groq fallback, invalid output, bounded corrective generation, cancellation without fallback, key selection and diagnostic redaction.
- Feedback tests reject fabricated evidence, selected invented numbers/dates and unsupported relative schedules. A schedule explicitly present in the supplied facts is allowed.
- API and session tests cover duplicate actions, accepted-answer preservation, Stop/Reset/disconnect, same-fact retry, separate histories, request/upload limits and private-file isolation.
- The six defects originally captured as strict expected failures are now ordinary passing regressions: chunked body limits, quoted `.env` comments, number-word grounding, grounded `this release`, duration-versus-delivery promises and reset cleanup.
- UI contract tests keep mobile help available, enforce readable control targets, preserve accessible status/error semantics and prevent decorative arrows from returning to action buttons.
- A request-cleanup race was found and fixed: Starlette's disconnect probe can consume a cancellation. An explicit completion event now terminates the watcher after a fast result or error. A regression test covers this case.
- On 18 November, the three launcher checks passed: direct `app.py` from `server/`, `python -m server` from the project folder and absolute `run.py` from another directory. Today's live check also launched the current code with `run.py` in the shared environment.

## Live voice and model results

### Post-remediation check

The [post-fix HTTP report](PHASE_1_POST_FIX_CHECK.json) used the selected `gemini-3.5-flash-lite` model and the same synthetic release-update WAV. Page assets, Whisper transcription, the stakeholder opening and follow-up, duplicate-answer protection, grounded coaching, retry isolation and reset passed. The generated rewrite preserved readiness and the two-working-day effort estimate without turning it into a delivery promise.

The current root configuration uses the legacy `GROQ_API_KEY_2` spelling. Python now accepts that spelling as an alias for `GROQ_API_KEY2`. If the preferred voice credential lacks Orpheus terms, DevBridge tries the primary Groq credential for that speech request. A [live fallback round trip](PHASE_1_VOICE_FALLBACK_CHECK.json) generated a valid 115,270-byte WAV and Whisper transcribed it as “DevBridge is ready for practice.” An immediate additional long synthesis hit the provider's rate limit; the UI preserves the text and exposes retry/continue behavior. This is a provider burst limit, not a failed coaching or session-state check.

### Earlier pipeline evidence

The original Groq key still returned `MODEL_TERMS_REQUIRED`. After the user added `GROQ_API_KEY2`, **Orpheus succeeded**. Python now prefers that key for TTS only; Whisper and GPT-OSS continue to use `GROQ_API_KEY`. No terms were accepted by this task.

The separate Orpheus-to-Whisper round trip generated 107,590 bytes of WAV audio and returned a recognizable transcript of the test sentence. The website-endpoint check then used an offline-generated, 219,278-byte WAV release update. Whisper returned:

> Search is ready for Friday, PDF export needs two more working days, I recommend releasing search first.

The final real-server run checked:

| Check | Result |
| --- | --- |
| Page and five browser resources | HTTP 200 |
| `/api/transcribe` with the synthetic answer | Passed |
| `/api/speak` using Orpheus and the second key | Valid WAV |
| Stakeholder opening and follow-up | Passed |
| Speech for the actual generated opening | Passed |
| Replayed answer submission | One accepted answer |
| Coaching and evidence validation | Passed after one guarded corrective generation |
| Speech for the generated coaching summary | Passed |
| Speech for the improved explanation | Passed, including two ordered segments |
| Retry creation | Same facts, separate empty second-attempt history |
| Reset | HTTP 204 |

Gemini initially timed out in direct checks. In the final HTTP run it returned rate-limit errors. Server logs confirmed automatic use of **Groq `openai/gpt-oss-20b`** for both stakeholder turns and coaching. The backup uses strict structured output and the same Python validators, following [Groq's structured-output API](https://console.groq.com/docs/structured-outputs).

A later [four-key Gemini comparison](GEMINI_MODEL_CHECK.md) on 19 November successfully invoked `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite` and `gemini-3-flash-preview` with all four newly configured credentials. Each model also passed a connection check through the app's Interactions adapter. The user then selected `gemini-3.5-flash-lite` as the application default. A Gemini-only check using the normal primary key completed both role-play and coaching through the Interactions API, and the reasoning trace contained two `reasoning_success` events for Gemini with no Groq fallback. The tested rewrite preserved the two-working-day effort estimate, unapproved scope and decision request. This is one controlled sample, not proof of behavior across every coaching case.

The server logs contain the fallback reason and model, not credentials. The temporary verification servers were stopped. The older user-started server was then restarted with the current code in the shared environment at `http://127.0.0.1:4317`, so the browser can use the updated voice key and fallback.

Generated audio from the final run:

| File | Duration |
| --- | --- |
| [Stakeholder opening](../output/audio/phase1-live-check/stakeholder-opening.wav) | 9.04 seconds |
| [Coaching summary](../output/audio/phase1-live-check/coaching-summary.wav) | 8.80 seconds |
| [Improved explanation](../output/audio/phase1-live-check/improved-explanation.wav) | 15.12 seconds |

These files prove audio generation and WAV assembly. They do not establish that browser playback, perceived voice quality or a physical speaker worked.

## Coaching review and remaining limitations

Earlier live outputs introduced an unsupported "next sprint" or "next cycle". Python now rejects selected such schedules and sends one specific corrective hint. If the second response also fails validation, the API returns an error and preserves the learner's accepted answer for retry.

Human review still found a limitation in the final sample: a stakeholder question described export as "two days later". The facts specify two additional working days of work, without an approved start or delivery date. The accepted rewrite also needs review for that distinction. Passing the numeric/date/schedule guards does not prove complete meaning preservation or coaching quality.

A clearer human-reviewed alternative for this test is:

> Search is ready for Friday. PDF export needs two additional working days, and the scope change is awaiting approval. I recommend releasing search first. Which option should we prioritize?

The complete Phase 1 acceptance gate remains pending human communication review and the physical/browser checks below.

## Browser access and device checks

Antigravity completed a real-browser QA pass on the earlier interface; its evidence and findings are preserved in [the independent report](ANTIGRAVITY_QA_REPORT.md). Those findings drove the current fixes. After the UI remediation, the Chrome attachment again returned **"The browser access host is unavailable"**, and the supplied companion-page attachment had `page_id: null`. Therefore the redesigned DevBridge interface has source, syntax, accessibility-contract and live-resource verification, but no new operated-browser screenshots or console capture from this session.

For ChatGPT desktop Work, the documented setup is to enable the Browser or Chrome plugin, keep Work locally selected, and share the relevant tab. Chrome also requires its extension and prompted permissions. See [OpenAI's browser setup guide](https://developers.openai.com/training/walkthroughs/using-your-computer-and-browser). Other clients can have different integration support.

Still requiring a post-fix browser pass: desktop/mobile rendering, JavaScript runtime console errors, actual microphone permission/recording, autoplay/Tap to Play, and the repaired recovery interactions. Physical speaker/headset playback and echo prevention also remain unverified. The backend cannot restore the unavailable browser host.

## Whether to replace Orpheus

**Keep Orpheus for now:** the second key resolved the provider block and real output passed. No replacement TTS provider was installed or selected.

If a replacement is wanted later:

| Option | Fit for this Python project | Trade-off |
| --- | --- | --- |
| Deepgram Aura-2 | Hosted REST API with Python examples, streamed output and WAV support. It could keep the existing `/api/speak` browser contract. | Requires a Deepgram account/key and provider billing. |
| Kokoro-82M | Open-weight model with a Python library and Apache-licensed weights; can run locally without a hosted TTS key. | Requires model files and local inference dependencies; benchmark latency on the target laptop first. |

These are integration recommendations based on the [Deepgram TTS documentation](https://developers.deepgram.com/docs/text-to-speech-latency) and [Kokoro's official model card](https://huggingface.co/hexgrad/Kokoro-82M). They were researched, not live-tested in this project. Aura-2 is the simpler hosted replacement; Kokoro is the option when avoiding a hosted TTS service matters more.

## Repeating the live checks

From `Internships/NETSOL/Voice_Coach`, using the shared interpreter:

```bash
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_providers --voice-only --diagnostic
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_providers --text-only --diagnostic
```

To repeat the HTTP check with a supplied WAV test answer:

```bash
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_website --audio /path/to/release-update.wav --report docs/PHASE_1_LIVE_CHECK.json --audio-output output/audio/phase1-live-check
```

The WAV should contain the same short search/Friday/PDF-export release update shown above. `check_website` starts and stops its own server. These commands make live provider requests; they never run automatically at application startup.

No remote Miro board or hosted site was changed.
