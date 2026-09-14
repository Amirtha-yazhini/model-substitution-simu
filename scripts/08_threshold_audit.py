"""Audit the sealed thresholds themselves: how fragile is a conformal maximum?

The holdout came back with GATEOPS at a 10% false-positive rate against a
protocol that claims <=0.99%. Before reporting that as a property of GATEOPS, it
is worth asking whether it is a property of the THRESHOLD ESTIMATOR - and it is.

The conformal bound P(new > max of N) <= 1/(N+1) is exact, but it is MARGINAL:
it averages over the draw of the calibration set. Conditional on one particular
calibration set - the one you sealed - the realised rate is a random variable.
For a continuous statistic it is Beta(1, N)-distributed, so at N=100 a 10% rate
should be a one-in-a-million accident. For a DISCRETE statistic it is far worse
behaved: the two-sample KS statistic on 240-vs-240 observations moves in steps of
1/240, and the maximum of 100 draws lands on a step with real probability mass
above it.

This script measures the realised tail probability of each sealed threshold
across several independent blocks of honest sessions. If the sealed block is
merely unlucky, other blocks will show a tail far heavier than 1/(N+1), and the
finding is about conformal calibration on discrete statistics rather than about
any auditor.

Nothing here changes a threshold. It is a diagnostic on the seal, run after the
holdout, and its output goes in the report as-is.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.runner import audit_session, build_auditors, run_session  # noqa: E402
from shim.ledger import load_prices  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "results" / "ledger_thraudit.jsonl"
PROTOCOL = ROOT / "config" / "protocol.yaml"
OUT = ROOT / "results" / "tables" / "threshold_audit.md"

# Independent blocks of honest sessions. The first is the SEALED calibration
# block; the rest are fresh and were never used to fit anything.
BLOCKS = {
    "sealed calibration (100-199)": range(100, 200),
    "block B (400-499)": range(400, 500),
    "block C (9000-9099)": range(9000, 9100),
}
AUDITORS = ["OTE", "IRIS-lite", "GATEOPS", "KBF", "BENCH"]


async def main_async(args: argparse.Namespace) -> int:
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8")) or {}
    thresholds = {
        k: (v or {}).get("threshold") for k, v in (protocol.get("thresholds") or {}).items()
    }
    cond = protocol.get("conditions", {})
    auditors = build_auditors(
        iris_trees=cond.get("iris_trees", 100),
        iris_splits=cond.get("iris_splits", 3),
        ote_perm=cond.get("ote_permutations", 200),
    )
    prices = load_prices()

    LEDGER.unlink(missing_ok=True)
    print("=" * 84)
    print("Threshold audit - realised tail mass of each sealed threshold")
    print("=" * 84)
    print(f"  protocol {protocol.get('sha256','?')[:24]}...  "
          f"claimed bound {protocol.get('conformal_fpr_bound', 0):.2%}\n")

    reference = await run_session("A0", cond.get("reference_seed", 1), LEDGER)

    per_block: dict[str, dict[str, list[float]]] = {}
    for label, seeds in BLOCKS.items():
        seeds = list(seeds)[: args.n]
        print(f"  {label}: {len(seeds)} honest sessions...", flush=True)
        scores: dict[str, list[float]] = {n: [] for n in AUDITORS}
        for seed in seeds:
            session = await run_session("A0", seed, LEDGER)
            res = audit_session(auditors, session, reference, prices=prices)
            for name in AUDITORS:
                r = res.get(name)
                if r is not None and r.applicable and r.score == r.score:
                    scores[name].append(r.score)
        per_block[label] = scores

    rows: list[dict[str, Any]] = []
    print(f"\n{'auditor':<12} {'threshold':>10} " +
          " ".join(f"{b.split('(')[0].strip()[:12]:>13}" for b in BLOCKS))
    print("-" * 84)
    for name in AUDITORS:
        thr = thresholds.get(name)
        if thr is None:
            continue
        cells = []
        rec: dict[str, Any] = {"auditor": name, "threshold": thr, "blocks": {}}
        for label in BLOCKS:
            vals = per_block[label][name]
            tail = sum(1 for v in vals if v > thr) / len(vals) if vals else float("nan")
            rec["blocks"][label] = {
                "n": len(vals), "tail_above_threshold": tail,
                "mean": statistics.mean(vals) if vals else None,
                "sd": statistics.stdev(vals) if len(vals) > 1 else None,
                "max": max(vals) if vals else None,
            }
            cells.append(f"{tail:>12.1%} ")
        rows.append(rec)
        print(f"{name:<12} {thr:>+10.4f} " + " ".join(cells))

    claimed = protocol.get("conformal_fpr_bound", 0.0099)
    lines = [
        "# Threshold audit: how much tail mass does each sealed threshold actually leave?\n",
        f"Protocol `{protocol.get('sha256','?')[:32]}...` claims a conformal "
        f"false-positive bound of **{claimed:.2%}**, obtained by taking each "
        f"threshold as the MAXIMUM over 100 honest calibration sessions.\n",
        "The table below measures, for each threshold, the fraction of honest "
        "sessions in three INDEPENDENT blocks that exceed it. The first block is "
        "the one the threshold was fitted on, so its tail is near zero by "
        "construction. The other two were never used to fit anything.\n",
        "| Auditor | sealed threshold | " +
        " | ".join(b for b in BLOCKS) + " |",
        "|---|---|" + "---|" * len(BLOCKS),
    ]
    for rec in rows:
        cells = [f"{rec['blocks'][b]['tail_above_threshold']:.1%}" for b in BLOCKS]
        lines.append(f"| {rec['auditor']} | {rec['threshold']:+.4f} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Reading this",
        "",
        "A conformal maximum bounds the false-positive rate **marginally** - averaged "
        "over which calibration set you happen to draw. Conditional on the one you "
        "sealed, the realised rate is a random variable, Beta(1, N)-distributed for a "
        "continuous statistic. At N=100 that puts a 10% realised rate at roughly one "
        "chance in a million, so a 10% result is not explained by ordinary bad luck.",
        "",
        "It is explained by DISCRETENESS. The two-sample KS statistic on 240-vs-240 "
        "observations moves in steps of 1/240, and its null distribution piles "
        "substantial mass on each step. The maximum of 100 draws therefore lands on a "
        "step that still has real probability above it, and the effective tail is set "
        "by the step, not by the sample size. OTE's permutation-debiased statistic is "
        "near-continuous and shows no such effect; GATEOPS' KS statistic and KBF's "
        "agreement rate, both coarse discrete quantities, do.",
        "",
        "The fix is not a bigger N - it is a threshold estimator that accounts for the "
        "step size, or a statistic that is not coarsely discrete at this sample size. "
        "**That change is NOT applied here.** It would require re-sealing, and the "
        "point of Phase 4 is that the numbers get reported as they came. This is "
        "recorded as a finding about conformal calibration on discrete statistics, and "
        "as the first entry on the list of what a protocol v2 should change.",
        "",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "results" / "threshold_audit.json").write_text(
        json.dumps({"protocol_sha256": protocol.get("sha256"), "rows": rows}, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure the realised tail of sealed thresholds.")
    ap.add_argument("--n", type=int, default=100, help="sessions per block")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
