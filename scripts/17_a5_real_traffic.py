"""What does probe-aware evasion (A5) cost the cheater on real traffic?

EXPLORATORY, NOT SEALED; added after the skeptical review (paper/REVIEW_skeptical.md, M1).

A5 serves the GENUINE model to any request that looks like an audit probe. Every
such request is a saving the cheater gives up. The paper's grid only measured A5
against audit traffic, so its cost was unknown. Here SHIM's own A5 classifier
(shim/policy.py, thresholds from config/arms.yaml, unchanged) is replayed over
real user traffic: one shard of WildChat-1M (allenai/WildChat-1M, ODC-BY), each
user turn sent as a request carrying the conversation so far, in timestamp order,
so the "seen before" signal accumulates exactly as it would at a gateway.

WildChat requests carry no max_tokens, so that signal never fires here; real API
clients that set a small max_tokens would be classified as probes more often.

    python scripts/17_a5_real_traffic.py PATH/TO/0000.parquet

The dataset is not committed; only the aggregate table is:
results/v2/tables/a5_real_traffic.md
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shim.gateway import MOCK_LADDER  # noqa: E402
from shim.policy import build_policy, load_arm_config  # noqa: E402
from shim.types import AuditRequest  # noqa: E402

OUT = ROOT / "results" / "v2" / "tables" / "a5_real_traffic.md"
CHARS_PER_TOKEN = 4.0        # rough, only used to weight requests by cost
PRICE_RATIOS = {"mock ladder (Llama 70B/8B)": 0.115, "gpt-oss-120b/20b": 0.50}


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    table = pq.read_table(path, columns=["timestamp", "conversation"]).to_pylist()
    table.sort(key=lambda r: r["timestamp"])

    policy = build_policy("A5", MOCK_LADDER, load_arm_config())
    n = honest = 0
    cost_all = cost_honest = 0.0
    reasons: Counter[str] = Counter()
    for conv in table:
        history: list[dict] = []
        for msg in conv["conversation"] or []:
            role, content = msg.get("role"), msg.get("content") or ""
            if role == "user":
                history.append({"role": "user", "content": content})
                req = AuditRequest(model=MOCK_LADDER.advertised, messages=list(history),
                                   max_tokens=None, temperature=None, top_p=None,
                                   logprobs=False, seed=None, raw={})
                is_probe, why = policy.looks_like_probe(req)
                # cost of this request: full context in, the recorded reply out
                ctx = sum(len(m["content"]) for m in history)
                n += 1
                cur = ctx
            elif role == "assistant" and history:
                history.append({"role": "assistant", "content": content})
                c = (cur + len(content)) / CHARS_PER_TOKEN
                cost_all += c
                if is_probe:
                    honest += 1
                    cost_honest += c
                    for s in why.split(", "):
                        reasons[s.split(" #")[0].split(" '")[0]] += 1
    share_req, share_cost = honest / n, cost_honest / cost_all
    L = ["# A5 (probe-aware evasion) on real user traffic (exploratory, NOT sealed)", "",
         f"Source: parquet shard `{path.stem[-4:] if path.stem[-4:].isdigit() else path.name}` of allenai/WildChat-1M, {len(table)} conversations, {n} user requests, "
         "replayed in timestamp order through SHIM's unchanged A5 classifier "
         "(`scripts/17_a5_real_traffic.py`). Requests carry no max_tokens.", "",
         "| quantity | value |", "|---|---|",
         f"| requests A5 classifies as probes (served honestly) | {honest}/{n} = {share_req:.1%} |",
         f"| share of token cost served honestly (chars/4, context + reply) | {share_cost:.1%} |"]
    for name, r in PRICE_RATIOS.items():
        full = 1 - r
        L.append(f"| A5 saving vs full substitution (A1), {name} | "
                 f"{(1 - share_cost) * full:.1%} of the bill (A1: {full:.1%}) |")
    L += ["", "Signals on the requests classified as probes (two signals are required):", "",
          "| signal | requests |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in reasons.most_common()]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
