# Analysis of the Antigravity Phase 1 QA pass

**Reviewed:** 19 November 2026, Asia/Karachi  
**Source report:** [ANTIGRAVITY_QA_REPORT.md](ANTIGRAVITY_QA_REPORT.md)  
**Evidence:** [Antigravity QA artifacts](../output/qa/antigravity/20261119-064606/)

## Conclusion

The QA pass is substantive and its main conclusion is justified: Phase 1 should not yet be accepted. The application pipeline works, but the product's central promise is accurate, respectful communication coaching. Confirmed meaning-preservation gaps can turn an effort estimate into a delivery commitment or turn unmeasured impact into zero impact, so pipeline success alone is insufficient.

The browser/provider distinction is important. Antigravity's live browser coaching used Groq `openai/gpt-oss-20b` because the then-configured `gemini-3.8-flash` hit its daily quota. Those results are evidence about the Groq fallback and the shared Python validation layer, not evidence about the output quality of `gemini-3.5-flash-lite`.

## Independently confirmed

- The package contains a report, 13 browser screenshots, console/network notes, provider diagnostics, coaching samples and a regression test module. No application source was changed by the QA pass.
- The added suite originally reproduced six known defects as strict expected failures. Those cases have since been converted into passing regressions.
- The screenshots confirm the complete desktop practice/retry UI, the questionable delivery-promise rewrite, the critique of a polite decision question and the missing mobile `How it works` navigation.
- Source inspection confirms the mobile navigation is hidden at `<=700px`, reset sends competing stop/delete requests, and stopping speech can leave the pending speech action in place.
- The report and text artifacts do not contain real API credentials.

## Model follow-up

The application default is now `gemini-3.5-flash-lite`. A Gemini-only live application check using the normal primary key completed both role-play and coaching without Groq fallback. Its tested rewrite preserved the supplied facts:

- search remains ready for Friday;
- PDF export needs two additional working days rather than being promised for a specific delivery date;
- the scope change still requires approval;
- the recommendation ends with a legitimate decision question.

This resolves the old primary-model quota blocker for the tested request. It does not prove that all Gemini responses preserve meaning. The shared validators that protect Gemini and fallback output have now been strengthened as described below.

## Priority assessment

1. **Acceptance blocker — meaning preservation.** Reject invented delivery timing, ungrounded number words, claims of zero impact when impact is merely unmeasured, and improper criticism of clear recommendations followed by decision questions. Remove the false positive for a grounded reference to `this release`.
2. **High-value interface fixes.** Restore mobile access to `How it works`; validate trimmed setup fields; give recovery buttons the correct action; and allow an immediate answer after stopping spoken playback.
3. **Hardening.** Normalize oversized chunked JSON errors, fix the quoted `.env` comment edge case, remove the reset request race, improve select presentation and enlarge small touch targets.

## Remediation completed

- Meaning guards now reject number-word inventions, delivery promises derived from work duration, zero-impact claims derived from unmeasured impact, unsupported schedules across actionable feedback fields and non-empty first-attempt comparisons. A grounded reference to `this release` is allowed.
- Chunked oversized JSON returns the application's `413 PAYLOAD_TOO_LARGE` envelope, and quoted `.env` values ignore matching quotes inside trailing comments.
- Whitespace-only setup input is rejected before submission; recovery labels match the failed stage; stopping speech restores answer controls; reset sends one cleanup request.
- Mobile help remains available. Body text and form controls are readable, action targets are at least 44 pixels, audience labels no longer clip, and decorative numbering/arrows were removed from actions.
- The visible product name is now **DevBridge** while source-folder and API paths remain compatible.
- Current verification: **95 tests passed, zero xfailed**, three launch modes passed, and the post-fix live model/session pipeline completed. A separate Orpheus fallback round trip passed; burst speech remains subject to provider rate limits.

## Evidence limitations

- The browser/network record is a curated summary plus screenshots, not a raw HAR or complete console export.
- Two files named as `390px` and `360px` viewport captures are stored at 500 pixels wide; the correctly sized setup-dialog captures and source CSS still support the mobile-navigation finding, but those two files do not independently prove their labelled viewport widths.
- The recorded reset test demonstrates the bad result when delete precedes stop, but it is a sequential surrogate rather than a captured concurrent race.
- Browser microphone input was exercised, but the original audio files were not retained in the evidence package.
- Saved diagnostics prove the Orpheus round trip, but do not independently identify which Groq credential was used. The current configuration has no recognized separate voice-key variable; a fresh check successfully used the documented fallback to the primary Groq key.
- Physical speakerphone/headset echo, perceived voice quality and real iOS/Android behavior remain untested.
- Human review of coaching usefulness remains required.

## Current acceptance status

**Implementation remediation complete; final acceptance still pending external checks.** The confirmed code defects are fixed and their regressions pass. Phase 1 acceptance should now wait for targeted browser testing of the redesigned interface, physical speaker/headset checks and a human reviewer to approve representative coaching outputs.
