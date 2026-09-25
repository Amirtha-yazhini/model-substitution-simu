"""Run many audit sessions across processes, returning RAW scores only.

Protocol v2 needs roughly 6,000 mock sessions - calibration, a 500-session
holdout, 30 seeds per arm and 200 per dilution rate - which is two hours on one
core and fifteen minutes on eight. Sessions are independent by construction
(each has its own seed), so they parallelise without changing a single number.

Workers return scores, p-values and e-values, never decisions. A decision needs
a threshold, and keeping the two apart means calibration and evaluation run the
same code path, and every decision is applied later from the sealed file.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Iterable

_STATE: dict[str, Any] = {}


def _init(ledger_dir: str, iris_trees: int, iris_splits: int, ote_perm: int,
          reference_seed: int, alpha: float) -> None:
    from shim.ledger import load_prices
    from shim.policy import load_arm_config

    from .runner import build_auditors

    _STATE.update(
        ledger=Path(ledger_dir) / f"ledger_{os.getpid()}.jsonl",
        auditors=build_auditors(iris_trees=iris_trees, iris_splits=iris_splits,
                                ote_perm=ote_perm),
        prices=load_prices(), arm_cfg=load_arm_config(),
        reference_seed=reference_seed, alpha=alpha, models={}, references={},
    )


def _models(ladder: str):
    from .runner import mock_models

    if ladder not in _STATE["models"]:
        _STATE["models"][ladder] = mock_models(ladder)
    return _STATE["models"][ladder]


def _reference(ladder: str):
    from .runner import run_session

    if ladder not in _STATE["references"]:
        _STATE["references"][ladder] = asyncio.run(run_session(
            "A0", _STATE["reference_seed"], _STATE["ledger"], models=_models(ladder)))
    return _STATE["references"][ladder]


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    """One session: {ladder, arm, seed, split, eps?} -> raw per-auditor results."""
    from .runner import audit_session, run_session

    cfg = _STATE["arm_cfg"]
    if job.get("eps") is not None:
        cfg = {**cfg, "A3": {**cfg["A3"], "eps": job["eps"]}}
    session = asyncio.run(run_session(job["arm"], job["seed"], _STATE["ledger"], cfg,
                                      _models(job["ladder"])))
    results = audit_session(_STATE["auditors"], session, _reference(job["ladder"]),
                            prices=_STATE["prices"], alpha=_STATE["alpha"])
    row = dict(job)
    row["auditors"] = {}
    for name, res in results.items():
        d = res.detail or {}
        p = d.get("p_value", d.get("fisher_p"))
        row["auditors"][name] = {
            "applicable": res.applicable,
            "score": None if res.score != res.score else res.score,
            "p_value": p,
            "e_value": res.e_value,
            "cost_usd": res.cost_usd,
            "reason": d.get("reason") if not res.applicable else None,
        }
    return row


def run_jobs(jobs: Iterable[dict[str, Any]], *, ledger_dir: Path, workers: int | None = None,
             iris_trees: int = 100, iris_splits: int = 3, ote_perm: int = 200,
             reference_seed: int = 1, alpha: float = 0.01, label: str = "") -> list[dict]:
    """Run jobs in parallel; results come back in job order."""
    jobs = list(jobs)
    ledger_dir.mkdir(parents=True, exist_ok=True)
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    t0 = time.perf_counter()
    out: list[dict] = []
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init,
        initargs=(str(ledger_dir), iris_trees, iris_splits, ote_perm, reference_seed, alpha),
    ) as ex:
        for i, row in enumerate(ex.map(run_job, jobs, chunksize=4), 1):
            out.append(row)
            if i % 100 == 0 or i == len(jobs):
                el = time.perf_counter() - t0
                print(f"  {label} {i}/{len(jobs)} sessions  [{el:.0f}s, "
                      f"~{el / i * (len(jobs) - i):.0f}s left]", flush=True, file=sys.stdout)
    return out
