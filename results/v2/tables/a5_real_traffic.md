# A5 (probe-aware evasion) on real user traffic (exploratory, NOT sealed)

Source: parquet shard `0000` of allenai/WildChat-1M, 59857 conversations, 172418 user requests, replayed in timestamp order through SHIM's unchanged A5 classifier (`scripts/17_a5_real_traffic.py`). Requests carry no max_tokens.

| quantity | value |
|---|---|
| requests A5 classifies as probes (served honestly) | 5705/172418 = 3.3% |
| share of token cost served honestly (chars/4, context + reply) | 0.6% |
| A5 saving vs full substitution (A1), mock ladder (Llama 70B/8B) | 88.0% of the bill (A1: 88.5%) |
| A5 saving vs full substitution (A1), gpt-oss-120b/20b | 49.7% of the bill (A1: 50.0%) |

Signals on the requests classified as probes (two signals are required):

| signal | requests |
|---|---|
| short prompt | 5682 |
| repeat | 5678 |
| closed-answer marker | 50 |
