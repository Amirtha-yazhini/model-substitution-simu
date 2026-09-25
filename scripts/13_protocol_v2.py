"""Protocol v2 - recalibrate, and seal every rule before any v2 evaluation runs.

v1 (`923a3d21...`, tag `frozen-v1`) stays exactly as sealed and is still
reported. v2 exists because v1's evaluation exposed two defects, and fixing a
threshold after seeing results is only honest under a NEW seal:

  1. The tie rule. 07_grid.py flagged at `score >= max`. The conformal bound
     P(fresh > max of N) <= 1/(N+1) is for STRICT exceedance, so every tie with
     the max became a flag. v2 flags at `score > threshold`.

  2. The calibration guarantee. A max over N honest sessions bounds the FPR
     MARGINALLY - averaged over calibration draws. v1 read GATEOPS' 6-10% fresh
     rate as a discreteness effect. Re-measured on 400 more honest sessions it
     is not: GATEOPS' KS statistic exceeds the v1 threshold on ~5% of fresh
     honest sessions in every block, and the sealed block simply drew a max
     that low (a ~1-in-300 draw). Discreteness never breaks the marginal bound;
     a single unlucky draw can. v2 therefore calibrates for a TRAINING-
     CONDITIONAL guarantee: with the max of N=300,
         P( realised FPR > alpha ) <= (1 - alpha)^N = 0.99^300 = 4.9%,
     which holds for discrete statistics too. The marginal bound tightens to
     1/301 = 0.33%.

v2 also seals what v1 left implicit, so no analysis choice can move after the
fact: every seed block, the dilution grid, the second (fitted) mock ladder and
the SHA-256 of its parameter file, the confidence-interval methods, and the
economics rules that define eps*.

    python scripts/13_protocol_v2.py            # calibrate and print, write nothing
    python scripts/13_protocol_v2.py --write    # write config/protocol_v2.yaml
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.batch import run_jobs  # noqa: E402
from arena.protocol import file_sha256, protocol_hash  # noqa: E402
from arena.runner import AUDITOR_SUITE, SUITE_PLAN, queries_per_session  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = ROOT / "config" / "protocol_v2.yaml"
V1 = ROOT / "config" / "protocol.yaml"
MOCK_FIT = "config/mock_fit.yaml"
OUT = ROOT / "results" / "v2"

ALPHA = 0.01
LADDERS = ["mock", "mock-fit"]
REFERENCE_SEED = 1
N_CAL = 300
IRIS_TREES, IRIS_SPLITS, OTE_PERM = 100, 3, 200

# Fresh seed blocks. Everything any v1 script or the v2 investigation has
# scored is listed in `seeds_already_seen` and avoided.
SEEDS = {
    "calibration": [10000, 10000 + N_CAL - 1],
    "holdout": [30000, 30499],
    "grid_arms": [40000, 40029],
    "eps_sweep": [50000, 50199],
}
SEEN = ["1", "100-499", "500-502", "700-719", "9000-9099",
        "20000-20299 (GATEOPS-only diagnosis of the v1 leak)"]
EPS_GRID = [0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20, 0.25, 0.35, 0.50]
SCORE_AUDITORS = ["OTE", "IRIS-lite", "GATEOPS", "KBF", "BENCH", "RUT"]


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrate and seal protocol v2.")
    ap.add_argument("--write", action="store_true", help="write config/protocol_v2.yaml")
    ap.add_argument("--force", action="store_true", help="overwrite an existing v2 seal")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()

    if PROTOCOL.exists() and args.write and not args.force:
        print("config/protocol_v2.yaml already exists. Re-sealing discards a commitment; "
              "pass --force only with a new protocol_version, and report it.")
        return 1

    v1 = yaml.safe_load(V1.read_text(encoding="utf-8"))
    print("=" * 84)
    print(f"Protocol v2 - calibration on {N_CAL} honest sessions per ladder")
    print("=" * 84)
    t0 = time.perf_counter()
    lo, hi = SEEDS["calibration"]
    jobs = [{"ladder": lad, "arm": "A0", "seed": s, "split": "calibration", "eps": None}
            for lad in LADDERS for s in range(lo, hi + 1)]
    rows = run_jobs(jobs, ledger_dir=OUT / "_ledger", workers=args.workers,
                    iris_trees=IRIS_TREES, iris_splits=IRIS_SPLITS, ote_perm=OTE_PERM,
                    reference_seed=REFERENCE_SEED, alpha=ALPHA, label="calibration")

    thresholds: dict[str, dict[str, Any]] = {}
    for lad in LADDERS:
        thresholds[lad] = {}
        print(f"\n[{lad}]  {'auditor':<10} {'n':>4} {'mean':>10} {'sd':>9} {'max':>10}  ties at max")
        for name in SCORE_AUDITORS:
            vals = [r["auditors"][name]["score"] for r in rows
                    if r["ladder"] == lad and r["auditors"][name]["applicable"]
                    and r["auditors"][name]["score"] is not None]
            if not vals:
                thresholds[lad][name] = {"threshold": None, "n_calibration": 0,
                                         "source": f"inapplicable on all {N_CAL} calibration sessions"}
                print(f"         {name:<10} {0:>4}  NOT APPLICABLE")
                continue
            thr = max(vals)
            ties = sum(1 for v in vals if v == thr)
            thresholds[lad][name] = {
                "threshold": float(thr),
                "scale": "score",
                "source": f"max of {len(vals)} honest calibration sessions",
                "n_calibration": len(vals),
                "ties_at_max": ties,
                "calibration_mean": statistics.mean(vals),
                "calibration_sd": statistics.stdev(vals),
            }
            print(f"         {name:<10} {len(vals):>4} {statistics.mean(vals):>+10.4f} "
                  f"{statistics.stdev(vals):>9.4f} {thr:>+10.4f}  {ties}")
        thresholds[lad]["FUSE"] = {"threshold": 1.0 / ALPHA, "scale": "e_value",
                                   "source": "Ville's inequality, not fitted"}

    doc: dict[str, Any] = {
        "protocol_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "supersedes": {
            "protocol_version": 1, "sha256": v1["sha256"], "tag": "frozen-v1",
            "status": "sealed; its results are kept and reported unchanged",
        },
        "changes_from_v1": [
            "decision rule: flag at score > threshold (v1: >=). The conformal bound is "
            "for strict exceedance; >= turned ties with the max into flags.",
            f"calibration: N={N_CAL} (v1: 100) for a training-conditional guarantee "
            f"P(realised FPR > {ALPHA}) <= (1-{ALPHA})^{N_CAL}; v1's 100 gave only a "
            f"marginal bound, and its GATEOPS threshold drew an unlucky max.",
            "second ladder 'mock-fit': OTE answer distributions and latency fitted to "
            "the census and live run; its parameter file is sealed by hash.",
            "seeds, dilution grid, CI methods and economics rules sealed up front.",
        ],
        "alpha": ALPHA,
        "decision_rule": ">",
        "fuse_rule": "e_product >= 1/alpha (Ville)",
        "calibration": {
            "n": N_CAL,
            "estimator": "max of N honest session scores",
            "marginal_fpr_bound": 1.0 / (N_CAL + 1),
            "training_conditional": {
                "claim": f"P(realised FPR > {ALPHA}) <= (1-{ALPHA})^N",
                "delta": (1 - ALPHA) ** N_CAL,
            },
        },
        "conditions": {
            "reference_seed": REFERENCE_SEED,
            "suite_plan": {n: {"cells": len(p), "repeats": r} for n, (p, r) in SUITE_PLAN.items()},
            "queries_per_session": queries_per_session(),
            "auditor_suite": dict(AUDITOR_SUITE),
            "ote_permutations": OTE_PERM,
            "iris_trees": IRIS_TREES,
            "iris_splits": IRIS_SPLITS,
            "ladders": LADDERS,
        },
        "sealed_inputs": {MOCK_FIT: file_sha256(ROOT / MOCK_FIT)},
        "seeds": SEEDS,
        "seeds_already_seen": SEEN,
        "evaluation": {
            "holdout": "A0, every holdout seed, both ladders",
            "grid": "arms A0-A11, every grid_arms seed, both ladders",
            "eps_sweep": {"arm": "A3", "eps": EPS_GRID,
                          "matched_benign_arm": "A11 on the same seeds"},
        },
        "analysis": {
            "rate_ci": "Wilson score, 95%",
            "auroc": "Mann-Whitney, ties half; arm sessions vs holdout",
            "power_target": 0.8,
            "family_fpr_budget": 0.05,
            "per_session_fpr": "holdout FPR, floored at the marginal bound 1/(N+1)",
            "monthly_spend_usd": 1000.0,
            "eps_star": "smallest swept eps at which some auditor (excluding RUT) reaches "
                        "the power target within its admissible session count and "
                        "within the adversary's saving",
            "eps_star_ci": {"method": "nonparametric bootstrap over sessions, "
                                      "resampling each eps batch and the holdout",
                            "replicates": 2000, "seed": 0},
            "primary_ladder": "mock (continuity with v1); mock-fit is the sensitivity analysis",
        },
        "thresholds": thresholds,
        "validity_gates": v1["validity_gates"],
    }
    doc["sha256"] = protocol_hash(doc)

    print("\n" + "=" * 84)
    print(f"Protocol v2 SHA-256: {doc['sha256']}")
    print(f"Calibrated in {time.perf_counter() - t0:.0f}s")
    if not args.write:
        print("\nDry run. Re-run with --write to seal config/protocol_v2.yaml.")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "calibration.jsonl").write_text(
        "\n".join(json.dumps(r, default=str) for r in rows) + "\n", encoding="utf-8")
    PROTOCOL.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"\nSealed {PROTOCOL.relative_to(ROOT)}. Commit it and tag frozen-v2 BEFORE "
          f"running scripts/14_evaluate_v2.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
