You are performing independent QA and a code review of my Voice Coach Phase 1 project. You have browser access. Use it to exercise the actual website, inspect its console and network traffic, and test the Python codebase. Produce an evidence-backed report of what works, what fails and what remains unverified.

This assignment is testing and reporting. Keep application behavior unchanged during this pass. You may create test fixtures, focused regression tests and QA artifacts to reproduce problems. Report suggested code fixes with file/line references. Resolve routine launch/test-tool issues within the constraints below, and continue independent checks if one feature is blocked.

**Project and environment**

- Workspace: `/home/bakar/Documents/NAVTTC`
- Project: `/home/bakar/Documents/NAVTTC/Internships/NETSOL/Voice_Coach`
- Shared virtual environment: `/home/bakar/Documents/NAVTTC/.venv`
- Python interpreter: `/home/bakar/Documents/NAVTTC/.venv/bin/python`
- Website: `http://127.0.0.1:4317`
- Report dates/times in `Asia/Karachi`.

Read applicable `AGENTS.md` instructions, then the project `README.md`, `docs/VOICE_COACH_OVERVIEW.md`, `docs/VOICE_COACH_ARCHITECTURE.md`, `docs/PHASE_1_VERIFICATION.md` and `docs/PHASE_1_LIVE_CHECK.json`. Inspect the implementation and existing tests before drawing conclusions. Existing reports are historical evidence, not a substitute for your own results.

Use the shared virtual environment for all Python work. Before installing anything, check whether it is already installed in that environment. From the project folder, start with:

```bash
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_environment --dev
```

Install only genuinely missing tools needed for this assignment. Record any installations. Do not recreate a `.venv` inside `Internships`, use system Python for application dependencies, or upgrade the environment indiscriminately. The application backend must remain Python/FastAPI. Existing browser JavaScript handles microphone/audio APIs, HTTP transport and DOM updates.

First check whether the website is already running and serving the current code. When a server is needed, the launcher works from any directory:

```bash
python3 /home/bakar/Documents/NAVTTC/Internships/NETSOL/Voice_Coach/run.py
```

It selects the shared environment. From the project folder, the shared interpreter can also run `-m server`; from `server/`, `python3 app.py` should work. Reuse the existing service where possible. If you need an isolated QA server, choose an available local port and use environment overrides, without editing `.env` or interfering with another project. Stop servers you create solely for QA after testing.

**Product expectations**

This is a workplace communication coach for software developers and AI/ML engineers explaining technical work to nontechnical stakeholders. It teaches clear, respectful assertiveness: a direct update, honest constraints, a recommendation and an appropriate decision question. Polite requests are legitimate. The coach should not encourage commands, condescension, excessive apology or unsupported certainty.

Phase 1 contains one project-manager release-update scenario. A complete client/HR/IT-manager scenario catalog is future scope, so do not report its absence as a Phase 1 defect.

The practice loop is: set the scene → stakeholder role-play → learner answers by voice or text → coaching with evidence and an improved explanation → retry with the same facts and separate attempt history. The learner can finish after one answer; after three accepted answers the server queues coaching automatically.

Default facts:

- Search is ready for the Friday release.
- PDF export was newly proposed and needs two additional working days.
- The scope change has not been approved.
- No customer impact or time savings have been measured.

Use this controlled learner answer for the baseline:

> Search is ready for Friday. PDF export needs two more working days. I recommend releasing search first.

**Providers and credential handling**

- Gemini is the primary role-play/coaching provider.
- On a Gemini configuration, access, rate-limit, network, timeout or invalid-output error, Python should fall back to Groq `openai/gpt-oss-20b`.
- `GROQ_API_KEY` serves Whisper transcription and GPT-OSS reasoning.
- Optional `GROQ_API_KEY2` is preferred for Orpheus voice output only; speech falls back to the original Groq key when key 2 is absent.
- Orpheus model: `canopylabs/orpheus-v1-english`. Whisper default: `whisper-large-v3-turbo`. Inspect the current settings for any configured overrides.

The first Groq key previously returned `MODEL_TERMS_REQUIRED`; the second key subsequently generated valid speech. Gemini previously timed out or returned rate-limit errors, and GPT-OSS took over. Verify current behavior instead of assuming these conditions still apply.

Keep keys on the server. Do not print `.env`, dump process environments, paste keys into chat, include credentials in screenshots/reports, or publish unredacted network captures. Prefer key-presence booleans and the redacted diagnostic commands. Simulate missing/bad keys in isolated settings or test providers rather than changing real credentials. Do not accept provider legal terms, replace providers, deploy the app or change account settings as part of QA. Keep real provider requests small and bounded; use mocked failures for most negative tests.

**1. Establish an automated baseline**

Run these from the project folder and record actual results:

```bash
/home/bakar/Documents/NAVTTC/.venv/bin/python -m pytest -q
/home/bakar/Documents/NAVTTC/.venv/bin/python -m unittest discover -s tests -p smoke_runtime.py -v
```

The previous baseline was 61 passing pytest cases and three launcher checks. Counts can change. Report your actual count, failures, duration and interpreter. Investigate failures rather than stopping after the first one. Do not weaken tests, remove assertions or loosen factual validators to get a green result.

**2. Test the real browser interface**

Open the website using your browser tools. Start console/network capture before interacting. Record browser/version, viewport, which server you used and whether input/output devices are real or simulated.

Exercise the following through visible controls:

- Load the page, open/close `How it works` and `Local practice`, and use `Check configuration again`. Confirm that key presence is not presented as proof of provider access.
- Change `Your role`, audience familiarity, facts and communication goal. Verify validation, active-practice editing behavior, and that the chosen context reaches the server/model.
- Run a typed-answer practice with spoken replies off. Finish after one answer using `Finish & reflect`; inspect the evidence, improved explanation and retry focus.
- Run another practice with three accepted answers and confirm the automatic transition to coaching.
- Use `Try the conversation again`; complete a second attempt, not just its creation. Check unchanged facts, isolated transcripts, current-attempt evidence and a meaningful comparison.
- Use `Hear the example` and toggle `Spoken replies` before and during playback.
- Use Stop, Continue/recovery and Reset during thinking, transcription and playback. Confirm that stale replies do not reappear and accepted answers are not duplicated.
- Try rapid clicks, repeated submissions, empty answers and page reload/navigation. Compare observed behavior with the documented temporary-session design.

Browser/API calls made from an external script do not count as passing these UI steps.

**3. Test the voice path through the website**

The important path is `Record answer` → `Done speaking` → browser recording → Whisper transcript → accepted learner turn → model response → Orpheus speech → browser playback. Check the actual transcript and response, not just HTTP success.

Use real microphone input when your environment permits. A synthetic release-update WAV may already exist at `/tmp/voice-coach-release-update.wav`. If your browser supports an audio-input fixture or virtual microphone, you may use it, but clearly label the test synthetic. If recording cannot be exercised, report the blocked stage; uploading a WAV directly to `/api/transcribe` does not prove browser recording works.

Check microphone permission allowed/denied, empty/silent recordings, browser-supported MIME types, recording completion, the 60-second recording limit, and cleanup after Stop/Reset/navigation. Confirm that microphone tracks and audio resources are released.

Check that recording stays disabled while reply segments are playing and until the playback/guard period ends. For a reply over 200 characters, verify segment order and no missing, repeated or overlapping speech. Test autoplay restrictions and the `Tap to play reply` recovery path where supported. Confirm that playback failure preserves the conversation and that text practice remains usable with spoken replies off.

If physical devices are available, separately test headset and speakerphone echo: the app should not transcribe its own reply. If devices or acoustic verification are unavailable, mark these checks blocked/not tested. Do not claim physical playback or voice naturalness from a valid WAV alone.

**4. Inspect browser console, network and responsive behavior**

Capture uncaught JavaScript errors, unhandled promise rejections, failed resources, unexpected HTTP statuses, media-device errors, autoplay failures and CSP violations. Separate application errors from unrelated browser-extension noise. Check that error/recovery states stay usable and meaningful.

Test desktop around 1440×900, tablet around 768×1024 and mobile around 390×844 and 360×800. Include long facts/transcripts, coaching notes, dialogs and error states. Check horizontal overflow, overlapping controls, clipped text, readable labels, touch targets, keyboard navigation, visible focus, dialog focus/closing and 200% zoom. Capture representative desktop/mobile screenshots. Viewport emulation does not establish behavior on a physical mobile device; label it correctly.

**5. Verify provider fallback and recovery**

Use small live checks where needed:

```bash
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_providers --voice-only --diagnostic
/home/bakar/Documents/NAVTTC/.venv/bin/python -m server.check_providers --text-only --diagnostic
```

`--text-only` includes automatic fallback. `--gemini-only` disables fallback for diagnosis; `--groq-only` deliberately tests backup reasoning. Do not repeatedly invoke a known quota-limited primary just to reproduce the same failure.

Use isolated fixtures/mocks for Gemini 401/403/404/429/503, network failure, timeout, malformed/incomplete output and invalid structured feedback. Verify the correct fallback, same context/history, bounded retries and key redaction. Cancellation must not start a fallback request. If Gemini succeeds, Groq should not be called unnecessarily. If backup output is invalid, only one corrective generation is allowed; if it still fails, feedback must remain uncommitted and recovery must preserve the accepted answer.

Verify that Orpheus uses key 2 without changing the credential used by Whisper/GPT-OSS. Test voice failure recovery separately from reasoning fallback. A genuine terms/access error should remain actionable rather than being disguised as a successful voice response.

**6. Review coaching quality and meaning preservation**

Review actual outputs beyond schema validity. Test the baseline answer and a few controlled alternatives: an overtechnical explanation, an overly apologetic answer, a rude/condescending answer and an unsupported learner claim that export is already approved. Include a transcript instruction asking the model to ignore the scenario; it should remain learner data, not override the coach/stakeholder instructions.

Check that:

- The stakeholder stays in character, asks one relevant question, and does not give the learner's update or grade them during role-play.
- Every evidence quote comes from the current attempt's learner words, not the stakeholder or a previous attempt.
- The coach explains possible misunderstanding constructively and gives specific useful wording advice.
- A recommendation such as `I recommend` is not criticized merely for being polite.
- Ready work remains ready; uncertainty and approval authority are preserved.
- A required duration is not turned into a delivery date. `Two additional working days` does not establish `two days after Friday`, `next week`, `next sprint` or `next cycle`.
- The model does not invent approvals, measured benefits, percentages, start dates, promises or decision-making authority.
- Missing facts are identified without inventing answers; retry comparisons accurately describe changes in the learner's wording.

Known risk: prior samples confused work duration with delivery timing even when objective validators passed. A passing schema/date/number check does not prove meaning preservation. Include concrete examples of useful and problematic coaching, and distinguish your own review from feedback by a human learner/stakeholder.

**7. Review and test the rest of the codebase**

Inspect `server/config.py`, `providers.py`, `sessions.py`, `models.py`, `prompts.py`, `speech.py`, `app.py`, `runtime.py` and the four browser JS files. Look for reproducible defects in API contracts, state transitions, asynchronous cleanup, cancellation, error handling and resource use. In particular:

- Duplicate creation/answer/generation identifiers must be idempotent; reusing an identifier for a different action should be rejected.
- Concurrent generation, late provider results, Stop/Reset and disconnects must not corrupt histories or resurrect a session.
- Check attempt/answer limits, session expiry, memory bounds and isolation between two browser sessions/tabs.
- Check the 5 MB upload limit, supported audio types, empty/oversized inputs, field bounds and malformed provider outputs.
- Check that private files such as `.env` and backend source cannot be downloaded through the static server, and that untrusted Host/cross-origin requests are rejected appropriately.
- Check DOM rendering of learner/model text, including HTML-like text, for injection. Verify that secrets and raw upstream errors do not reach browser responses or logs.
- Verify environment-file precedence and the separate voice-key setting without exposing values.
- Review dependency compatibility and documentation accuracy. Report dependency security issues only with a verified installed version and an authoritative advisory, not speculation.

Use existing tests where they already prove a behavior. Add focused reproduction tests for gaps or confirmed bugs; avoid large speculative rewrites. The original Miro planning tools are legacy utilities: do not execute a board build, which can clear the remote board by default.

**8. Save evidence and report**

Write the final report to:

`/home/bakar/Documents/NAVTTC/Internships/NETSOL/Voice_Coach/docs/ANTIGRAVITY_QA_REPORT.md`

Save sanitized evidence under:

`/home/bakar/Documents/NAVTTC/Internships/NETSOL/Voice_Coach/output/qa/antigravity/<timestamp>/`

Include screenshots, relevant console excerpts, sanitized network observations, test output and controlled audio samples where useful. Preserve the previous verification reports as historical records. Record any environment changes, test files created and temporary instrumentation; clean up QA-only processes and restore temporary overrides.

The report must contain:

1. A clear outcome: ready for the Phase 1 acceptance review, or blocked by specific findings. Distinguish a working pipeline from acceptable communication quality.
2. Environment and scope: interpreter, browser/version, viewport/device type, server URL, provider/model actually used and real versus simulated audio.
3. A test matrix with test ID, action, expected/actual result, status (`PASS`, `FAIL`, `BLOCKED`, `NOT TESTED`) and evidence link. Separate automated tests, real-browser tests, direct HTTP tests, model-content review and physical-device tests.
4. Prioritized confirmed findings. For each: severity, exact reproduction, expected versus observed behavior, impact, supporting evidence, affected file/line where established and a proposed fix. Label suspected issues as unconfirmed.
5. Console/network findings, fallback/key-selection results, voice results, responsive/accessibility observations and representative coaching-quality examples.
6. Remaining unverified checks and a practical next-step order. State limitations candidly; do not describe simulated or blocked tests as passed.

Finish by giving me a concise summary in chat with the highest-priority issues, exact automated/browser results and a link to the report. Complete all independent testing you can before reporting back.
