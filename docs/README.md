# DevBridge documentation

Version 3.0 documents the workplace communication coach for software developers and AI/ML engineers. It includes source-backed research, proposed practice situations, role-play and coaching behavior, examples, architecture and delivery phases.

[Parent folder](../README.md) | [Repository guide](../../../../README.md)

For the Python prototype, start with the [project run guide](../README.md) and [verification report](PHASE_1_VERIFICATION.md). The research PDF remains the earlier design reference.

## Current material

| Entry | Purpose |
| --- | --- |
| [Current PDF documentation](../output/pdf/Voice_Coach_Project_Plan.pdf) | Main report and revised project plan. |
| [VOICE_COACH_OVERVIEW.md](VOICE_COACH_OVERVIEW.md) | Short explanation of the new product and Phase 1. |
| [VOICE_COACH_ARCHITECTURE.md](VOICE_COACH_ARCHITECTURE.md) | Stakeholder/coach separation, speech services, session data and recovery rules. |
| [PHASE_1_VERIFICATION.md](PHASE_1_VERIFICATION.md) | Current tests, live provider results, browser limits and TTS alternatives. |
| [PHASE_1_POST_FIX_CHECK.json](PHASE_1_POST_FIX_CHECK.json) | Post-remediation live HTTP evidence and current provider limitation. |
| [PHASE_1_VOICE_FALLBACK_CHECK.json](PHASE_1_VOICE_FALLBACK_CHECK.json) | Live Orpheus credential fallback and rate-limit evidence. |
| [PHASE_1_LIVE_CHECK.json](PHASE_1_LIVE_CHECK.json) | Earlier complete live HTTP pipeline evidence. |
| [ANTIGRAVITY_QA_ANALYSIS.md](ANTIGRAVITY_QA_ANALYSIS.md) | Independent findings, evidence caveats and completed remediation. |
| [ANTIGRAVITY_POST_FIX_QA_PROMPT.md](ANTIGRAVITY_POST_FIX_QA_PROMPT.md) | Focused handoff for real-browser verification of the repaired UI. |
| [AI_ML_SCENARIO_CHECK.md](AI_ML_SCENARIO_CHECK.md) | Live Gemini test using an AI/ML model-rollout conversation. |
| [voice_coach_documentation.json](voice_coach_documentation.json) | Editable content used to generate the current PDF. |
| [PDF builder](build_project_plan_pdf.py) | Generates the current PDF from the JSON content. |

The previous Markdown project plan was deleted at the user's request. Current short reference documents describe the revised concept. Research findings are distinguished from proposed scenarios and untested implementation choices in the PDF.

## Regenerating the PDF

Check whether `reportlab` is already installed in the selected documentation environment before installing anything. Then run from the repository root:

```bash
python3 Internships/NETSOL/Voice_Coach/docs/build_project_plan_pdf.py
```

Render the resulting PDF to page images and inspect every page before sharing. The PDF records the design at its documentation stage. Current runtime and test status is maintained in the verification report.
