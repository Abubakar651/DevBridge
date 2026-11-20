# DevBridge - workplace communication overview

18 November 2026 | Python / FastAPI Phase 1 prototype

## Purpose and audience

Help software developers and AI/ML engineers explain work, business impact, limitations and recommendations to clients, project managers, IT managers and HR. Communication should be understandable, confident and respectful, with the amount of technical detail matched to the listener's actual familiarity.

The coach teaches a clear position without unnecessary hesitation or dismissiveness. It preserves uncertainty and supports polite requests or decision questions when they are appropriate.

## Practice cycle

1. Select a workplace situation and stakeholder, then provide known facts, constraints and the communication goal.
2. Speak with an AI role-playing that stakeholder and respond to relevant follow-up questions.
3. Finish practice and receive one strength, specific feedback and an improved explanation.
4. Hear the example, then try the same situation again with the same facts.

Proposed situations include progress updates, deadlines, scope changes, blockers, AI limitations and HR contribution or workload discussions. These are curriculum choices, not a proven ranking of conversation frequency. Read the [PDF research report](../output/pdf/Voice_Coach_Project_Plan.pdf) for the evidence and limitations.

## Phase 1

Prove one project-manager progress-update scenario through role-play, feedback, improved wording and a second attempt. Include manual recording controls, visible Stakeholder/Coach modes, transcript, Stop/Reset and recovery. Verify meaning preservation and usefulness as well as the voice pipeline.

## Implementation

**Learner speech -> browser recording -> Groq Whisper -> Gemini -> Groq Orpheus -> spoken output**

Whisper handles transcription; Orpheus handles speech generation. Gemini has separate stakeholder and coach actions. Python and FastAPI own provider calls, practice history, coaching and retry state. JavaScript is limited to browser I/O and interface updates. A mobile PWA follows after the coaching behavior is demonstrated.

The first release-update exercise is implemented. All other stakeholder roles remain later-phase work. See [verification status](PHASE_1_VERIFICATION.md) for tests and live-service limitations.
