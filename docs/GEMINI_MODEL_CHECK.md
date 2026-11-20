Gemini model and key comparison — 19 November 2026, Asia/Karachi

All four distinct credentials (`GEMINI_API_KEY`, `GEMINI_API_KEY2`, `GEMINI_API_KEY3`, `GEMINI_API_KEY4`) successfully generated replies with three models. These were small connection tests using the prompt “Connection test: reply only with Ready.” Groq fallback was disabled. Key values are omitted.

[Detailed results](GEMINI_MODEL_CHECK.json)

| Model | Result across all four keys | Successful direct-call time range |
| --- | --- | --- |
| `gemini-3.1-flash-lite` | Passed; HTTP 200 and `Ready.` from every key | 0.89–2.70 s |
| `gemini-3.5-flash-lite` | Passed; HTTP 200 and `Ready.` from every key | 2.78–5.48 s |
| `gemini-3-flash-preview` | Passed; HTTP 200 and `Ready.` from every key | 1.11–1.35 s |
| `gemini-3.6-flash` | Timed out after 30 seconds on every key | — |
| `gemini-3.1-pro-preview` | HTTP 429: quota/resource exhausted on every key | — |
| `gemini-2.5-flash` | HTTP 404: provider reports unavailable to new users | — |
| `gemini-2.5-flash-lite` | HTTP 404: provider reports unavailable to new users | — |
| `gemini-2.5-pro` | HTTP 404: provider reports unavailable to new users | — |

The batch made 32 direct `generateContent` probes: 12 passed and 20 failed. Each successful model was then tested through the application's existing Interactions API adapter, with JSON output and fallback disabled:

| Model | Credential label tested | App adapter result |
| --- | --- | --- |
| `gemini-3.1-flash-lite` | `GEMINI_API_KEY3` | Passed; `Ready`, 2.35 s |
| `gemini-3.5-flash-lite` | `GEMINI_API_KEY4` | Passed; `Ready`, 4.51 s |
| `gemini-3-flash-preview` | `GEMINI_API_KEY2` | Passed; `Ready`, 1.00 s |

An additional direct application-adapter check of `gemini-3.1-flash-lite` using `GEMINI_API_KEY` also returned `Ready`.

These results confirm successful invocation, not full role-play/coaching quality, load capacity or guaranteed future availability. Only a small greeting was generated, and timing is a single sample per key/model pair.

After this comparison, the user selected `gemini-3.5-flash-lite` and the application's default model was changed accordingly. A later Gemini-only application check using the normal primary `GEMINI_API_KEY` completed both role-play and coaching through the Interactions API with no Groq fallback. The other credentials were supplied individually only in the temporary comparison process; normal runtime key rotation was not added.
