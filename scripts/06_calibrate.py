"""Phase 4 - fit thresholds on the DEV split only, then seal them.

This phase is the one that separates the project from the work it criticises. Not
because sealing is clever, but because it removes an option: once the hash is
written and tagged, a bad holdout cannot be fixed by moving a threshold. Every
number after this point is reported as it comes.

Protocol:
  * Thresholds are fitted ONLY on honest (A0) calibration sessions. No arm is
    scored, or even run, during calibration - an adversarial arm cannot leak into
    a threshold it never touched.
  * Each threshold is the MAXIMUM over N calibration scores. Under exchangeability
    that is a conformal bound: a fresh honest session exceeds the max of N with
    probability at most 1/(N+1). At N=100 that is under 1%, achieved by
    construction rather than by fitting a quantile to a handful of points.
  * FUSE's threshold is NOT fitted. Ville's inequality already gives it e >= 1/alpha
    at level alpha for free, and fitting one would throw away the anytime-validity
    that is the entire reason to use e-values.
  * Everything that could move a number goes into the sealed file: seeds, suite
    plan, repeat counts, permutation count, forest size, auditor hyperparameters,
    and the git commit. A threshold without its conditions is not reproducible.

    python scripts/06_calibrate.py            # fit and print, write nothing
    python scripts/06_calibrate.py --write    # write config/protocol.yaml + hash
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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

from arena.runner import (  # noqa: E402
    AUDITOR_SUITE, SUITE_PLAN, audit_session, build_auditors,
    queries_per_session, run_session,
)
from shim.ledger import load_prices  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "results" / "ledger_calib.jsonl"
PROTOCOL = ROOT / "config" / "protocol.yaml"

# Seed blocks are disjoint by construction so calibration, holdout and the arms
# can never silently share a session. That is the cheapest possible insurance
# against the most embarrassing possible bug.
SEED_REFERENCE = 1
SEEDS_CALIB = range(100, 200)        # 100 sessions -> conformal FPR <= 1/101
SEEDS_HOLDOUT = range(9000, 9050)    # never touched until Phase 5
ALPHA = 0.01

IRIS_TREES, IRIS_SPLITS, OTE_PERM = 100, 3, 200


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def protocol_hash(doc: dict[str, Any]) -> str:
    """SHA-256 over the canonical protocol, excluding the hash field itself."""
    body = {k: v for k, v in doc.items() if k != "sha256"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def main_async(args: argparse.Namespace) -> int:
    LEDGER.unlink(missing_ok=True)
    prices = load_prices()
    auditors = build_auditors(
        iris_trees=IRIS_TREES, iris_splits=IRIS_SPLITS, ote_perm=OTE_PERM
    )
    t0 = time.perf_counter()

    print("=" * 78)
    print("Phase 4 - threshold calibration on the DEV split (honest sessions only)")
    print("=" * 78)
    print(f"  {queries_per_session()} queries/session, "
          f"{len(list(SEEDS_CALIB))} calibration sessions")
    print(f"  suites: " + ", ".join(
        f"{n} ({len(p)}x{r})" for n, (p, r) in SUITE_PLAN.items()))

    print("\nReference session (A0, seed 1)...")
    reference = await run_session("A0", SEED_REFERENCE, LEDGER)

    print("Calibrating...", flush=True)
    scores: dict[str, list[float]] = {n: [] for n in auditors}
    scores["FUSE"] = []
    inapplicable: dict[str, int] = {n: 0 for n in scores}

    for i, seed in enumerate(SEEDS_CALIB, 1):
        session = await run_session("A0", seed, LEDGER)
        results = audit_session(auditors, session, reference, prices=prices, alpha=ALPHA)
        for name, res in results.items():
            if res.applicable and res.score == res.score:
                scores[name].append(res.score)
            else:
                inapplicable[name] += 1
        if i % 20 == 0:
            print(f"  {i}/{len(list(SEEDS_CALIB))} sessions", flush=True)

    n_calib = len(list(SEEDS_CALIB))
    conformal = 1.0 / (n_calib + 1)

    print(f"\n{'auditor':<12} {'n':>4} {'mean':>10} {'sd':>9} {'max':>10}  threshold")
    print("-" * 78)
    thresholds: dict[str, Any] = {}
    for name in list(auditors) + ["FUSE"]:
        vals = scores[name]
        if name == "FUSE":
            # Not fitted. See the module docstring.
            thresholds[name] = {
                "threshold": 1.0 / ALPHA,
                "scale": "e_value",
                "source": "Ville's inequality, not fitted",
                "n_calibration": len(vals),
            }
            print(f"{name:<12} {len(vals):>4} {'-':>10} {'-':>9} {'-':>10}  "
                  f"e >= {1/ALPHA:.0f} (Ville, unfitted)")
            continue
        if not vals:
            thresholds[name] = {
                "threshold": None,
                "source": f"inapplicable on all {inapplicable[name]} calibration sessions",
                "n_calibration": 0,
            }
            print(f"{name:<12} {0:>4} {'-':>10} {'-':>9} {'-':>10}  "
                  f"NOT APPLICABLE on this fleet")
            continue
        thr = max(vals)
        thresholds[name] = {
            "threshold": float(thr),
            "scale": "score",
            "source": f"max of {len(vals)} honest calibration sessions (conformal)",
            "conformal_fpr_bound": conformal,
            "n_calibration": len(vals),
            "calibration_mean": statistics.mean(vals),
            "calibration_sd": statistics.stdev(vals) if len(vals) > 1 else 0.0,
            "n_inapplicable": inapplicable[name],
        }
        sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
        print(f"{name:<12} {len(vals):>4} {statistics.mean(vals):>+10.4f} {sd:>9.4f} "
              f"{max(vals):>+10.4f}  {thr:+.4f}")

    doc: dict[str, Any] = {
        "protocol_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "alpha": ALPHA,
        "conformal_fpr_bound": conformal,
        # Everything below changes the numbers, so everything below is sealed.
        "conditions": {
            "reference_seed": SEED_REFERENCE,
            "calibration_seeds": [min(SEEDS_CALIB), max(SEEDS_CALIB)],
            "holdout_seeds": [min(SEEDS_HOLDOUT), max(SEEDS_HOLDOUT)],
            "suite_plan": {n: {"cells": len(p), "repeats": r}
                           for n, (p, r) in SUITE_PLAN.items()},
            "queries_per_session": queries_per_session(),
            "auditor_suite": dict(AUDITOR_SUITE),
            "ote_permutations": OTE_PERM,
            "iris_trees": IRIS_TREES,
            "iris_splits": IRIS_SPLITS,
            "ladder": "mock",
        },
        "thresholds": thresholds,
        "validity_gates": {
            "min_cells_ote": 8,
            "applicable_false_is_uninformative": True,
            "one_sided_tests": True,
            "note": (
                "A method that cannot run returns uninformative, never consistent. "
                "Changing any threshold after sealing requires a new protocol "
                "version and a new git tag, and must be reported as such."
            ),
        },
    }
    doc["sha256"] = protocol_hash(doc)

    print("\n" + "=" * 78)
    print(f"Protocol SHA-256: {doc['sha256']}")
    print(f"Calibrated in {time.perf_counter()-t0:.0f}s")

    if not args.write:
        print("\nDry run. Re-run with --write to seal config/protocol.yaml.")
        return 0

    if PROTOCOL.exists() and not args.force:
        old = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8")) or {}
        print(f"\nconfig/protocol.yaml already exists (sha {old.get('sha256','?')[:16]}...).")
        print("Re-sealing discards a commitment that has already been made. "
              "Pass --force only with a new protocol_version, and say so in the report.")
        return 1

    PROTOCOL.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(f"\nSealed {PROTOCOL.relative_to(ROOT)}")
    print("Now commit it and tag:  git tag frozen-v1")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Fit and seal auditor thresholds.")
    ap.add_argument("--write", action="store_true", help="write config/protocol.yaml")
    ap.add_argument("--force", action="store_true", help="overwrite an existing seal")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
