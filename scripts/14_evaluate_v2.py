"""Protocol v2 evaluation - holdout, grid and dilution sweep, both ladders.

Nothing here fits or decides anything. It verifies the v2 seal (including the
hash of config/mock_fit.yaml), runs every session the protocol names, and writes
RAW scores. Decisions are applied from the sealed thresholds in
scripts/15_paper.py, so the rule that turns a score into a flag lives in one
place and cannot drift between tables.

    python scripts/14_evaluate_v2.py               # ~6,100 sessions, ~20 min on 8 cores
    python scripts/14_evaluate_v2.py --workers 4

Output: results/v2/sessions.jsonl, one session per line.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.batch import run_jobs  # noqa: E402
from arena.protocol import load_sealed  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = ROOT / "config" / "protocol_v2.yaml"
OUT = ROOT / "results" / "v2"
ARMS = [f"A{i}" for i in range(12)]


def seeds(pair) -> range:
    lo, hi = pair
    return range(lo, hi + 1)


def plan(protocol) -> list[dict]:
    S = protocol["seeds"]
    jobs: list[dict] = []
    for lad in protocol["conditions"]["ladders"]:
        jobs += [{"ladder": lad, "arm": "A0", "seed": s, "split": "holdout", "eps": None}
                 for s in seeds(S["holdout"])]
        jobs += [{"ladder": lad, "arm": arm, "seed": s, "split": "grid", "eps": None}
                 for arm in ARMS for s in seeds(S["grid_arms"])]
        for eps in protocol["evaluation"]["eps_sweep"]["eps"]:
            jobs += [{"ladder": lad, "arm": "A3", "seed": s, "split": "eps", "eps": eps}
                     for s in seeds(S["eps_sweep"])]
        jobs += [{"ladder": lad, "arm": "A11", "seed": s, "split": "eps", "eps": None}
                 for s in seeds(S["eps_sweep"])]
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the protocol v2 evaluation.")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()

    protocol = load_sealed(PROTOCOL)
    cond = protocol["conditions"]
    print("=" * 84)
    print("Protocol v2 evaluation")
    print("=" * 84)
    print(f"  protocol sha256 {protocol['sha256'][:32]}...  VERIFIED")
    for rel, h in protocol.get("sealed_inputs", {}).items():
        print(f"  sealed input {rel} {h[:16]}...  VERIFIED")

    jobs = plan(protocol)
    print(f"  {len(jobs)} sessions across ladders {cond['ladders']}\n")
    t0 = time.perf_counter()
    rows = run_jobs(jobs, ledger_dir=OUT / "_ledger", workers=args.workers,
                    iris_trees=cond["iris_trees"], iris_splits=cond["iris_splits"],
                    ote_perm=cond["ote_permutations"], reference_seed=cond["reference_seed"],
                    alpha=protocol["alpha"], label="evaluate")
    for r in rows:
        r["protocol_sha256"] = protocol["sha256"]
        for a in r["auditors"].values():
            if a.get("reason") is None:
                a.pop("reason", None)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sessions.jsonl").write_text(
        "\n".join(json.dumps(r, default=str, separators=(",", ":")) for r in rows) + "\n",
        encoding="utf-8")
    print(f"\nWrote results/v2/sessions.jsonl ({len(rows)} sessions) "
          f"in {time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
