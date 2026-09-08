# Free-tier capability coverage

Measured: 2026-09-08T07:50:42+00:00

Empirically measured, not taken from documentation. This table is the applicability-coverage result: it determines which auditors can run on which endpoints at all.


## Per-model capabilities

| Provider | Model | Works | usage | cached_tokens | logprobs | sys_fp | reasoning tok | 16-tok probe viable |
|---|---|---|---|---|---|---|---|---|
| groq | `openai/gpt-oss-120b` | yes | yes | no | no | yes | 36 | no |
| groq | `openai/gpt-oss-20b` | yes | yes | no | no | yes | 35 | no |
| groq | `qwen/qwen3.8-27b` | yes | yes | no | no | yes | - | yes |
| groq | `qwen/qwen3.6-27b` | yes | yes | no | no | yes | - | no |
| groq | `allam-2-7b` | yes | yes | no | no | yes | - | yes |
| groq | `groq/compound-mini` | yes | yes | no | no | no | - | no |
| google | `gemini-2.5-flash` | yes | yes | no | no | no | - | yes |
| google | `gemini-2.5-pro` | **HTTP 404** | - | - | - | - | - | - |
| google | `gemini-3-flash-preview` | yes | yes | no | no | no | - | yes |
| google | `gemma-4-31b-it` | **HTTP 500** | - | - | - | - | - | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | yes | yes | yes | no | no | 26 | no |
| openrouter | `nvidia/nemotron-3-super-120b-a12b:free` | yes | yes | yes | no | no | 36 | no |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | yes | no | no | no | no | - | no |
| openrouter | `google/gemma-4-31b-it:free` | **HTTP 429** | - | - | - | - | - | - |

## Auditor applicability (the coverage result)

| Auditor | Requires | Applicable endpoints | Coverage |
|---|---|---|---|
| OTE @16 tok (as published) | no hidden reasoning | 4/11 | 36% |
| OTE @256 tok (adapted) | text only | 10/11 | 91% |
| IRIS-lite | text only | 11/11 | 100% |
| KBF | text only | 11/11 | 100% |
| BENCH (Cai et al.) | text only | 11/11 | 100% |
| GATEOPS latency | timing only | 11/11 | 100% |
| GATEOPS billing | `cached_tokens` | 2/11 | 18% |
| RUT | logprobs | 0/11 | 0% |
| (any usage-based) | `usage` block | 10/11 | 91% |

## Finding: hidden reasoning has repriced cheap auditing

4/11 working endpoints spend tokens on hidden reasoning before emitting any answer. Bruckner's published protocol caps completions at 16 tokens; on a reasoning endpoint that returns an EMPTY string with `finish_reason=length`, so the probe fails rather than answers.

| Endpoint | reasoning tokens | completion tokens | answer |
|---|---|---|---|
| groq/`openai/gpt-oss-120b` | 36 | 46 | `42` |
| groq/`openai/gpt-oss-20b` | 35 | 45 | `42` |
| openrouter/`nvidia/nemotron-3-ultra-550b-a55b:free` | 26 | 30 | `42` |
| openrouter/`nvidia/nemotron-3-super-120b-a12b:free` | 36 | 45 | `42` |

Bruckner reported excluding 0.76% of his census for unexpected reasoning traces. On this 2026 free-tier fleet the affected share is far larger, and per-probe cost rises from ~16 tokens to whatever the model spends thinking. That inflates the audit side of the break-even calculation in idea.md C3a: the cheapest known auditing method got more expensive because the fleet changed, not because the method changed.


## Provider notes

- **groq** (secondary_workhorse): /models ok, 14 slugs listed, 6 probed working.
- **google** (first_party_reference): /models ok, 55 slugs listed, 2 probed working.
- **openrouter** (rationed): /models ok, 428 slugs listed, 3 probed working. **Rate-limited during probe.**
