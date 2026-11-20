# AI/ML scenario check

**Date:** 19 November 2026, Asia/Karachi  
**Scenario:** Customer-support routing model rollout risk  
**Audience:** Nontechnical project manager  
**Provider:** Gemini `gemini-3.5-flash-lite`, fallback disabled

## Scenario facts

- The routing model works on historical test data.
- It has not been evaluated on requests from the newest client.
- Security review and production approval are pending.
- Production monitoring setup needs three working days.
- No customer impact or time savings have been measured.

The communication goal was to explain why the model is not ready for a customer-wide rollout, recommend a limited internal pilot after approval and ask the project manager to decide whether to proceed.

## Tested learner answer

> The routing model works on historical test data, but it has not been evaluated on the newest client's requests. Security review and production approval are pending, and monitoring setup needs three working days. I recommend a limited internal pilot after approval before any customer rollout. Would you approve that plan?

## Live result

Gemini completed both role-play and coaching through the application adapter. No Groq fallback occurred.

The stakeholder asked:

> Can you give me an update on the customer-support routing model and what you recommend we do next?

The improved message preserved the important facts:

> The routing model works on historical test data, but it has not been evaluated on the newest client's requests. Security review and production approval are still pending, and monitoring setup requires three working days. I recommend a limited internal pilot after we receive approval, and I would like your decision on whether to proceed with this approach.

## Assessment

| Check | Result |
| --- | --- |
| Gemini role-play and coach completed | Passed |
| Exactly one relevant stakeholder question | Passed |
| Historical testing not presented as proven live performance | Passed |
| Pending reviews and approval authority preserved | Passed |
| Three working days remained an effort estimate | Passed |
| No invented dates, metrics, savings or impact | Passed |
| Evidence quote came from the learner's current answer | Passed |
| First-attempt comparison remained empty | Passed |
| Clear decision question treated as already legitimate | Needs improvement |

The coach labelled `Would you approve that plan?` as an Assertiveness improvement even though it acknowledged that asking directly was good. Its suggested replacement requested essentially the same decision. This is not a factual error, but it is weak coaching: when the learner already gives a clear recommendation and decision question, the coach should focus on genuinely missing information such as pilot scope, success criteria, human-review ownership or rollback conditions.

## Verdict

**Pass with a coaching-quality concern.** The model and factual safeguards generalized to the AI/ML context. The current Phase 1 application still exposes only the `release-update` scenario ID; this was an alternate-context provider test, not a second selectable website exercise.
