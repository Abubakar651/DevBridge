# Phase 3 Qualitative Pilot & Completion Gate Validation

**Status:** Phase 3 Complete (`DEV-31` Workstream: `DEV-32`–`DEV-35`)  
**Date:** 23 November 2026  
**Scope:** Exploratory qualitative validation across 5 learner tracks and 3 stakeholder reviewer lenses, plus automated 10-cycle silence/retry/stop/reset durability verification.

> **Evidential boundary:** Per `Voice_Coach_Project_Plan.pdf` (Page 8), this pilot is exploratory qualitative validation of message clarity, meaning preservation, and coaching usefulness. It is not a population study and does not promise a guaranteed workplace reaction.

---

## 1. Phase 3 Capabilities Validated

1. **Automatic Voice-Activity & Silence Detection (VAD) with Manual Controls (`DEV-33`, `web/audio.js`, `web/session.js`):**
   - Web Audio API `AudioContext` + `AnalyserNode` time-domain RMS monitor inside `Recorder`.
   - Ignores pre-speech silence; once speech exceeds `speechThreshold` (`0.02`) for `>= 240ms`, a continuous post-speech pause below `silenceThreshold` (`0.012`) for `>= 2200ms` auto-finishes recording when `#auto-silence` (*Auto-send on pause*) is checked.
   - Retains manual `Record answer`, `Done speaking`, and `Stop` controls at all times.
2. **Stakeholder Pressure / Difficulty Levels (`DEV-32`, `DEV-34`, `server/scenario.py`, `web/index.html`):**
   - Configurable `#difficulty` selector (`Supportive · warm & guiding`, `Standard · realistic check-in`, `Skeptical · high-scrutiny pushback`) injected into `ROLEPLAY_PROMPT` and `COACH_PROMPT`.
3. **5-Signal Communication Checklist Attempt Comparison (`DEV-32`, `DEV-34`, `web/app.js`):**
   - Compares Attempt `N-1` vs. Attempt `N` using the same scenario facts across all 5 checklist signals (`Audience clarity`, `Structure and relevance`, `Assertiveness`, `Respect`, `Accuracy and next steps`) with `Improved ✓`, `Strong ✓`, `Focus next`, and `Practising now` badges in `#checklist-comparison`.
4. **Playback & Text Draft Recovery (`DEV-34`, `web/session.js`, `web/app.js`):**
   - Preserves `lastTranscribedText` into `#answer-text` if a downstream step fails after Whisper transcription, and adds `#use-example-button` (*Retry with example draft*) to load `feedback.improvedMessage` directly into the next attempt's composer.

---

## 2. Exploratory Pilot Matrix (5 Learner Sessions × 3 Reviewer Perspectives)

Each pilot scenario compared a rough first attempt against a second attempt coached by DevBridge using identical `knownFacts`. Reviewer lenses evaluated whether **Outcome**, **Constraint / Boundary**, **Recommendation**, and **Next Step** were restatable without decoding jargon.

| Learner Track & Scenario | Stakeholder & Difficulty | Attempt 1 (Rough Wording) | Coaching & Checklist Signals Flagged | Attempt 2 (Retry Wording) | Reviewer Restatement Check |
| --- | --- | --- | --- | --- | --- |
| **L1 — AI/ML Engineer**<br>`churn-pitch` | **VP of Operations**<br>`skeptical` | *"We got 0.84 F1 and 89% precision on historical data. We need 4 more weeks for CRM."* | Flagged `Audience clarity` (raw F1 metric) & `Assertiveness` (missing approval ask). | *"Over four weeks we organized customer data and tested a model that spots cancellation risk. Connecting alerts to the CRM takes four more weeks, and live retention savings are not measured yet. Would you approve the four-week CRM rollout?"* | **Reviewer 1 (Executive / Client lens):** Outcome, 4-week CRM ask, and unmeasured live savings all restatable in one read. |
| **L2 — Software Developer**<br>`two-day-delay` | **Project manager**<br>`standard` | *"The webhook retry bug took longer than expected so the payment migration is late by two days."* | Flagged `Structure and relevance` & `Accuracy and next steps` (no decision ask on staged rollout). | *"Core payment checkout is ready and tested. Fixing the edge-case retry issue needs two additional working days, and existing users are unaffected. I recommend keeping checkout on track and adding the retry fix after those two working days. Does that priority work?"* | **Reviewer 2 (PM / IT Ops lens):** Ready work vs. 2-day effort duration and safety of current users clearly separated. |
| **L3 — Software Developer**<br>`client-scope-change` | **Client**<br>`skeptical` | *"We can't add bulk invoice export now because you didn't include it in the original scope."* | Flagged `Respect` (blaming phrasing) & `Assertiveness` (no trade-off recommendation). | *"The agreed billing dashboard is tested and ready to launch. Adding bulk invoice export requires three additional working days of engineering and verification. I recommend launching the billing dashboard now and scheduling bulk export next—which option do you prefer?"* | **Reviewer 1 (Executive / Client lens):** Respectful tone restored; checklists showed `Respect: Improved ✓` and `Assertiveness: Improved ✓`. |
| **L4 — AI/ML Engineer**<br>`ai-ml-limits` | **IT manager**<br>`skeptical` | *"The ticket classifier is 90% accurate on our 100 test cases so it is ready to deploy."* | Flagged `Accuracy and next steps` (overstating 10/100 error rate as live readiness). Grounding guard blocked any claim of proven live accuracy. | *"In 100 reviewed test tickets, 10 needed correction, and performance on live customer traffic has not been established. I recommend a limited pilot with human review before wider rollout. Can we align on that pilot scope?"* | **Reviewer 2 (PM / IT Ops lens):** Honest 10-in-100 error rate and human-review pilot gate preserved without false guarantees. |
| **L5 — Software Developer**<br>`hr-contribution` | **HR representative**<br>`supportive` | *"We just wrote some scripts for the weekly spreadsheet report."* | Flagged `Assertiveness` (minimizing personal ownership with vague team pronouns). Grounding guard preserved unmeasured time savings. | *"I automated our weekly operational report and wrote the handover notes so teammates no longer rebuild the spreadsheet manually. Time savings have not been measured yet. My personal contribution was building the automation and handover workflow."* | **Reviewer 3 (HR lens):** Personal ownership separated from team outcome while keeping time savings honestly unmeasured. |

---

## 3. Useful vs. Misleading Feedback Audit & Documented Boundary Cases

- **Useful coaching patterns confirmed:**
  - Exact verbatim quoting from current-attempt `USER` messages prevented fabricated criticism.
  - The 5-signal checklist comparison strip (`#checklist-comparison`) gave immediate visual confirmation when a flagged dimension (e.g., `Respect` or `Audience clarity`) was resolved in Attempt 2 (`Improved ✓`).
- **Remaining boundary cases & guardrails documented:**
  1. **Background noise & VAD threshold:** In noisy environments where ambient RMS remains above `0.012`, automatic pause detection may wait for manual completion; learners can uncheck `Auto-send on pause` (`#auto-silence`) or click `Done speaking` (`#done-button`) at any time.
  2. **Strict numeric grounding on early finish:** `validate_feedback()` intentionally rejects any new digit or number word in `improvedMessage` absent from `knownFacts`, so rewrites remain strictly anchored to scenario facts even on 1-turn early finishes.
  3. **No guaranteed workplace outcome:** Improvements reflect communication clarity against the 5-dimension rubric, not a guarantee of stakeholder approval in real organizational settings.
