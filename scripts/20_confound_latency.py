"""How much of the load-balancing confound comes from the second provider's latency?

EXPLORATORY, NOT SEALED; added after the second skeptical review
(paper/REVIEW_skeptical_2.md, M2).

A11 routes traffic across honest providers of the right model. In both simulated
pairs the honest second provider (`alternate-70b`) has HAND-WRITTEN timing: in the
hand-written pair 0.85 s mean and CV 0.45 against the genuine model's 1.10 s and
0.30; the fitted pair rescales the genuine model's measured latency by those same
ratios, because no second free provider of gpt-oss-120b could be measured. This
script re-runs the 200 sealed A11 sessions (same seeds) with the second
provider's timing set to:

  none      identical to the genuine model
  measured  18% faster, the gap measured live between gpt-oss-20b and 120b
  sealed    unchanged (re-run on 20 seeds only, to check the rows reproduce)

Everything else, including the sealed v2 thresholds and the honest reference,
is unchanged. A3 (eps = 0.10) sessions are taken from the committed v2 results,
since A3 never routes to the second provider.

    python scripts/20_confound_latency.py

Output: results/v2/tables/confound_latency.md
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arena.protocol import load_sealed  # noqa: E402

_spec = importlib.util.spec_from_file_location("paper15", ROOT / "scripts" / "15_paper.py")
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

OUT = P.TAB / "confound_latency.md"
LEDGER = ROOT / "results" / "v2" / "_ledger" / "ledger_confound_latency.jsonl"
MEASURED_RATIO = 0.538 / 0.656          # live medians, results/live/summary.json
SETTINGS = {"none": 1.0, "measured": MEASURED_RATIO, "sealed": None}

_W: dict = {}


def models_for(ladder: str, setting: str):
    from arena.runner import mock_models
    from shim.mock import MOCK_MODELS

    base = mock_models(ladder) or dict(MOCK_MODELS)
    base = dict(base)
    ratio = SETTINGS[setting]
    if ratio is None:
        return base
    g, alt = base["genuine-70b"], base["alternate-70b"]
    changes = {"latency_mean_s": g.latency_mean_s * ratio, "latency_cv": g.latency_cv}
    if getattr(g, "latency_log_samples", None):
        changes["latency_log_samples"] = [v + math.log(ratio) for v in g.latency_log_samples]
        changes["latency_bandwidth"] = g.latency_bandwidth
    base["alternate-70b"] = dataclasses.replace(alt, **changes)
    return base


def _init(conditions):
    from arena.runner import build_auditors
    from shim.ledger import load_prices
    from shim.policy import load_arm_config

    _W.update(auditors=build_auditors(iris_trees=conditions["iris_trees"],
                                      iris_splits=conditions["iris_splits"],
                                      ote_perm=conditions["ote_permutations"]),
              prices=load_prices(), cfg=load_arm_config(), refs={},
              ref_seed=conditions["reference_seed"])


def job(j):
    from arena.runner import audit_session, mock_models, run_session

    ladder, setting, seed, alpha = j
    if ladder not in _W["refs"]:
        _W["refs"][ladder] = asyncio.run(run_session("A0", _W["ref_seed"], LEDGER, models=mock_models(ladder)))
    session = asyncio.run(run_session("A11", seed, LEDGER, _W["cfg"], models_for(ladder, setting)))
    res = audit_session(_W["auditors"], session, _W["refs"][ladder], prices=_W["prices"], alpha=alpha)
    row = {"ladder": ladder, "arm": "A11", "seed": seed, "split": f"latency-{setting}", "eps": None,
           "auditors": {}}
    for name, r in res.items():
        d = r.detail or {}
        row["auditors"][name] = {"applicable": r.applicable,
                                 "score": None if r.score != r.score else r.score,
                                 "p_value": d.get("p_value", d.get("fisher_p")),
                                 "e_value": r.e_value, "cost_usd": r.cost_usd}
    return row


def main() -> int:
    protocol = load_sealed(ROOT / "config" / "protocol_v2.yaml")
    sealed_rows = [r for r in P.load_jsonl(P.V2 / "sessions.jsonl") if r["protocol_sha256"] == protocol["sha256"]]
    lo, hi = protocol["seeds"]["eps_sweep"]
    ladders = protocol["conditions"]["ladders"]
    jobs = [(lad, s, seed, protocol["alpha"]) for lad in ladders for s in ["none", "measured"]
            for seed in range(lo, hi + 1)]
    jobs += [(lad, "sealed", seed, protocol["alpha"]) for lad in ladders for seed in range(lo, lo + 20)]
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 2, initializer=_init,
                             initargs=(protocol["conditions"],)) as ex:
        new = list(ex.map(job, jobs, chunksize=4))
    for r in new:
        r["protocol_sha256"] = protocol["sha256"]

    ev = P.Evidence(protocol, sealed_rows + new)
    names = ["OTE", "IRIS-lite", "GATEOPS", "KBF", "BENCH", "FUSE"]
    L = ["# Load-balancing confound vs the second provider's latency (exploratory, NOT sealed)", "",
         "Generated by `scripts/20_confound_latency.py`. A11 re-run on the 200 sealed seeds with the honest "
         "second provider's timing changed; sealed v2 thresholds; A3 at eps = 0.10 from the committed results. "
         f"'measured' = {MEASURED_RATIO:.2f} x the genuine model's latency (the live 20b/120b gap).", ""]
    for lad in ladders:
        a3 = ev.sel(lad, "eps", "A3", 0.10)
        sealed_a11 = ev.sel(lad, "eps", "A11")
        check = [r for r in ev.rows if r["ladder"] == lad and r["split"] == "latency-sealed"]
        ref = {r["seed"]: r for r in sealed_a11}
        same = sum(all(abs((c["auditors"][n]["score"] or 0) - (ref[c["seed"]]["auditors"][n]["score"] or 0)) < 1e-9
                       for n in names[:-1]) for c in check)
        L += [f"## {P.LADDER_NAME[lad]}", "",
              f"Reproducibility check: {same}/{len(check)} re-run sealed A11 sessions match the committed scores.", "",
              "| second provider's timing | " + " | ".join(f"{n}: flags A11 / AUROC A3 vs A11" for n in names) + " |",
              "|---|" + "---|" * len(names)]
        for label, rs in [("sealed (hand-written gap)", sealed_a11),
                          ("measured gap (18% faster)", ev.sel(lad, "latency-measured", "A11")),
                          ("no gap (same as genuine)", ev.sel(lad, "latency-none", "A11"))]:
            cells = []
            for n in names:
                k, m = ev.rate(rs, n)
                auc = P.auroc(P.Evidence.scores(a3, n), P.Evidence.scores(rs, n))
                cells.append(f"{P.pct_ci(k, m, 0)} / {auc:.2f}")
            L.append(f"| {label} | " + " | ".join(cells) + " |")
            print(lad, label, cells[2], cells[5])
        k3, m3 = ev.rate(a3, "GATEOPS")
        L += ["", f"For comparison, GATEOPS flags A3 (eps = 0.10) on {P.pct_ci(k3, m3, 0)} of sessions.", ""]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
