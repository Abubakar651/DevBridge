nb

# DevBridge - Python Phase 1

DevBridge is a workplace communication coach for software developers and AI/ML engineers. The first exercise is a project-manager release update: practise the conversation, receive feedback and better wording, then retry with the same facts. The existing `Voice_Coach` source-folder name is retained to avoid breaking local paths.

The application backend is **Python with FastAPI**. Python owns the scenario, prompts, provider integrations, validation, practice state, conversation history, answer counting, coaching, retry isolation, idempotency and speech segmentation. There is no Node application server or npm setup.

The four files in `web/` that use JavaScript only handle browser device access, same-origin HTTP requests, audio playback and DOM updates. Browser microphone recording and audio playback require those browser APIs. HTML and CSS define the interface.

[Parent folder](../README.md) | [Research and design PDF](output/pdf/Voice_Coach_Project_Plan.pdf) | [Verification status](docs/PHASE_1_VERIFICATION.md)

## Check the existing virtual environment first

The application uses the existing shared environment at `/home/bakar/Documents/NAVTTC/.venv`. The nested `Voice_Coach/.venv` has been removed.

Inspect the shared environment from any directory:

```bash
/home/bakar/Documents/NAVTTC/.venv/bin/python /home/bakar/Documents/NAVTTC/Internships/NETSOL/Voice_Coach/server/check_environment.py
```

This only inspects the selected interpreter and installed package versions. It never installs anything. FastAPI, Uvicorn, HTTPX, Pydantic and requests are already installed in the shared environment. On 19 November, pytest was checked, found missing and installed with its missing test dependencies to run the regression suite. No runtime packages were added.

If working in a different checkout, locate its existing virtual environment and check that interpreter first. Only if packages are actually missing should you install those missing dependencies. `requirements.txt` lists runtime dependencies; `requirements-dev.txt` adds pytest.

## Run the Python application

Sta00rt from any directory:

```bash
python3 /home/bakar/Documents/NAVTTC/Internships/NETSOL/Voice_Coach/run.py
```

The launcher automatically selects the shared virtual environment. If your terminal is already in `Voice_Coach/server`, this also works:

```bash
python3 app.py
```

From the project folder, `python -m server` uses the same launcher. Direct execution of `app.py` now enters through the Python package, fixing the relative-import error.

Open <http://127.0.0.1:4317>. Stop the server with Ctrl+C. Use Python 3.11 or newer. The port and host are configurable in `.env`.

Restart an already running server after code changes. A process started before these changes will not load the new fallback or the second voice-key setting until restarted.

Provider configuration is read from the ignored project `.env`, with fallback to the repository-root `.env`. Environment variables take precedence. `.env.example` lists the names. Real keys remain on the Python server. After adding a key, use **Local practice -> Check configuration again** in the interface.

Gemini is the primary reasoning provider. If its key is missing or its request/output fails, Python uses Groq `openai/gpt-oss-20b` with the same scenario, transcript and validators. Cancellation does not trigger fallback. Invalid backup output gets at most one corrective generation; rejected feedback is never committed. `GROQ_REASONING_MODEL` configures the backup model.

`GROQ_API_KEY` handles Whisper input and backup reasoning. The optional `GROQ_API_KEY2` handles **Orpheus output only**; when absent, speech uses `GROQ_API_KEY`. Keep both keys in the ignored `.env`. The second key passed a live Orpheus/Whisper round trip on 19 November. If another key returns `MODEL_TERMS_REQUIRED`, review the model terms in the organization associated with that key. Spoken replies can be switched off while practising in text.

## Use Phase 1

1. Review the release-update facts, learner role, audience familiarity and communication goal.
2. Start practice. Respond to the simulated project manager by recording an answer or typing it.
3. Finish after one to three answers. The coach gives evidence-linked feedback, an improved explanation and a retry focus.
4. Try again. Python starts a fresh attempt with the same context and keeps the previous attempt separate for comparison.
5. Stop cancels current work. Reset clears the temporary server session and the interface.

Sessions are held only in Python process memory, expire after one hour of inactivity and are removed on Reset. They are not saved in a database. A process restart clears them. Browser page exit also attempts a best-effort session reset. The local prototype is not a shared production deployment.

## Run checks

The startup checks use standard-library `unittest` and the already installed runtime packages:

```bash
cd /home/bakar/Documents/NAVTTC/Internships/NETSOL/Voice_Coach
/home/bakar/Documents/NAVTTC/.venv/bin/python -m unittest discover -s tests -p smoke_runtime.py -v
```

They start and stop real local servers, check all three launch paths, and verify page/configuration responses and session creation/reset. They do not call live AI providers.

The broader fixture suite uses optional pytest. Check whether it is installed before adding anything:

```bash
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_environment --dev
```

When pytest is available, run `/home/bakar/Documents/NAVTTC/.venv/bin/python -m pytest -q` from the project folder.

The test suite uses Python fixtures and mock provider responses. It does not need API keys. Live provider checks make small real requests and are run explicitly, never automatically on startup.

Useful live-check options:

```bash
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_providers
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_providers --voice-only
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_providers --text-only
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_providers --groq-only
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_providers --gemini-only
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_providers --list-gemini-models
```

`--model MODEL_ID` tests a different Gemini model without editing `.env`. `--diagnostic` shows provider error details with configured keys redacted. See the verification report for passed checks and remaining live-service limitations.

`--text-only` includes automatic fallback; `--gemini-only` explicitly disables it. `--groq-only` deliberately leaves Gemini unconfigured for that check. [server/check_website.py](server/check_website.py) runs the website's actual HTTP endpoints on its own temporary server with a supplied WAV answer. It can save generated speech and a JSON report; it does not test a browser, physical microphone or speakers.

## Source map

| Entry                                     | Responsibility                                                        |
| ----------------------------------------- | --------------------------------------------------------------------- |
| [run.py](run.py)                           | Start the application using the shared NAVTTC virtual environment.    |
| [server/app.py](server/app.py)             | FastAPI routes, local-origin protection and disconnect cancellation.  |
| [server/sessions.py](server/sessions.py)   | Python practice state, accepted answers, feedback, retries and reset. |
| [server/providers.py](server/providers.py) | Gemini Interactions API and Groq HTTPX adapters.                      |
| [server/models.py](server/models.py)       | Pydantic input/output validation and feedback evidence checks.        |
| [server/prompts.py](server/prompts.py)     | Separate stakeholder and coach instructions.                          |
| [server/speech.py](server/speech.py)       | Plain-text preparation and bounded speech segments.                   |
| [web/](web/index.html)                     | Browser interface, recording and playback.                            |
| [tests/](tests/test_api.py)                | Python API, workflow and provider tests.                              |
| [docs/](docs/README.md)                    | Overview, architecture, research and current verification status.     |

## Original Miro tools

The original Miro board, generator, saved manifest describe the superseded technical-interview concept. They have not been republished. `build_voice_coach_board.py` and `miro_client.py` remain Python planning utilities.

An actual board build clears existing items by default; `--keep-existing` appends. Implementation work did not run a board build.

## Deploy on AWS EC2 (HTTPS + Caddy)

Ready-to-use templates live in [`deploy/`](deploy/devbridge.service):

- [`deploy/ec2_setup.sh`](deploy/ec2_setup.sh) — Ubuntu 24.04 bootstrap script installing Python, Git, and Caddy, setting up `/opt/devbridge/.venv`, copying `.env.example`, and registering `systemd`.
- [`deploy/devbridge.service`](deploy/devbridge.service) — `systemd` unit running a single `--workers 1` Uvicorn process bound locally on `127.0.0.1:4317` (required because sessions live in memory).
- [`deploy/Caddyfile`](deploy/Caddyfile) — HTTPS reverse proxy forwarding `X-Forwarded-Proto: https` (required for browser microphone access, HSTS headers, and PWA `/sw.js` registration).

Set these Phase 4 variables in `/opt/devbridge/.env` (`chmod 600`) alongside your provider keys:

- `ALLOWED_HOSTS=your-domain.example.com`
- `RATE_LIMIT_PER_MINUTE=30`
- Optional `DEMO_ACCESS_TOKEN=...` to require `X-DevBridge-Token` / `Authorization: Bearer ...` on `/api/*`.
