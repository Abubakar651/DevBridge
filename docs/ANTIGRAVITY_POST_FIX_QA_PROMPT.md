# DevBridge post-fix browser QA prompt

Independently test the current local DevBridge application at `http://127.0.0.1:4317`. This is a verification pass: do not edit application source, credentials, provider terms or external services. Keep API keys out of screenshots, logs and reports.

Use the existing shared environment at `/home/bakar/Documents/NAVTTC/.venv`. Before installing anything, run `python -m server.check_environment --dev`; do not install packages that are already present. The app should already be running, but if it is not, launch it with:

```bash
/home/bakar/Documents/NAVTTC/.venv/bin/python /home/bakar/Documents/NAVTTC/Internships/NETSOL/Voice_Coach/run.py
```

First run the automated baseline from the project directory. Expect 95 or more passing tests, zero failures and zero xfails:

```bash
/home/bakar/Documents/NAVTTC/.venv/bin/python -m pytest -q
```

Then use the real browser UI and DevTools to verify the following.

## Responsive interface

- Confirm the visible product name is `DevBridge`.
- Test `1440×900`, `1024×768`, `768×1024`, `390×844`, `360×800` and 200% zoom.
- Confirm there is no horizontal overflow, clipped audience option or unreadably small task text.
- Confirm `How it works` remains visible and opens its dialog on both mobile widths.
- Confirm Start, Send, Stop, Reset, close-dialog and recovery controls have practical touch targets; inspect computed size where useful.
- Confirm the three-stage order remains Set the scene → Conversation → Coaching on single-column layouts.
- Exercise keyboard navigation, focus rings, dialog Escape/close and focus return.

## Repaired interactions

- Enter only spaces in scenario facts and goal. The browser must block submission with a field-specific message and must not send `POST /api/practice`.
- Complete a typed practice and verify role-play, Finish & reflect, coaching and Try the conversation again.
- During a role-play generation error, recovery should say `Retry response`; during a coaching error it should say `Try feedback again`.
- Stop during spoken playback. Record and Send must become usable immediately without replaying the stopped speech.
- Reset an active practice. Network evidence should show one `DELETE /api/practice/{id}` cleanup request, not a competing `POST /stop` plus DELETE race.
- Confirm loading states expose `aria-busy=true`, errors receive focus, and no duplicate transcript turns appear.

## Content and voice

- Use the supplied release facts. Verify generated coaching never changes “needs two additional working days” into a delivery promise, never turns unmeasured impact into zero impact, and does not criticize a clear `I recommend …` statement merely because it ends with a decision question.
- Verify the live microphone path if permission is available. Keep synthetic fixtures clearly labelled as synthetic.
- The preferred separate Groq voice credential may return `MODEL_TERMS_REQUIRED`; the server should automatically try the primary Groq credential. Provider rate limits are acceptable only when the UI preserves text/state and offers a safe retry path.
- Do not accept provider terms on the user's behalf.

## Evidence and report

Capture sanitized screenshots for desktop, tablet and both mobile sizes, plus relevant console/network evidence. Distinguish browser observations, source/test evidence, synthetic audio and physical-device tests. Do not claim speakerphone/headset echo or voice naturalness without testing actual hardware.

Write the final report to:

`docs/ANTIGRAVITY_POST_FIX_QA_REPORT.md`

Use a clear outcome: `PASS`, `PASS WITH EXTERNAL LIMITATIONS`, or `BLOCKED`. List exact remaining defects with reproduction steps and evidence paths. Preserve the original `ANTIGRAVITY_QA_REPORT.md` as historical evidence.
