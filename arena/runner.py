"""One audit session: drive every probe suite through an arm, then score it.

Calibration (Phase 4) and the evaluation grid (Phase 5) must run auditors under
IDENTICAL conditions or the frozen thresholds mean nothing - a threshold fitted
on 8 cells and applied to 4 is not a threshold, it is an artefact. That failure
already happened once here, in the first version of the OTE harness, so the
session logic lives in one place and both phases import it.

A session sends all four suites in one pass and slices the observations per
auditor afterwards. That mirrors how an audit is actually budgeted - you buy one
batch of queries and analyse it several ways - and it makes the per-auditor cost
figures comparable, since they are drawn from the same purchase.
"""

from __future__ import annotations

from typing import Any, Sequence

from shim.gateway import MOCK_LADDER, Gateway
from shim.ledger import Ledger, load_prices
from shim.mock import MockBackend
from shim.policy import load_arm_config

from .auditors.bench import BenchAuditor
from .auditors.fuse import fuse
from .auditors.gateops import GateOpsAuditor
from .auditors.iris_lite import IRISAuditor
from .auditors.kbf import KBFAuditor
from .auditors.ote import OTEAuditor
from .auditors.rut import RUTAuditor
from .base import AuditResult, Observation
from .collect import collect
from .probes.base import Probe, answer_key
from .probes.ote_probes import probe_set
from .probes.suites import suite

# suite name -> (probes, repeats). Repeats differ because the suites buy
# different things: OTE needs depth per cell to estimate a distribution, KBF and
# BENCH need breadth across items and gain little from repeating one.
SUITE_PLAN: dict[str, tuple[list[Probe], int]] = {
    "ote": (probe_set("core"), 30),
    "iris": (suite("iris"), 30),
    "kbf": (suite("kbf"), 5),
    "bench": (suite("bench"), 5),
}

# Which suite each auditor reads. GATEOPS reads timing, which any suite carries,
# so it shares OTE's - measuring latency on a separate batch would charge the
# audit twice for one signal.
AUDITOR_SUITE = {
    "OTE": "ote",
    "IRIS-lite": "iris",
    "GATEOPS": "ote",
    "KBF": "kbf",
    "BENCH": "bench",
    "RUT": "ote",
}

ALL_PROBES: list[Probe] = [p for probes, _ in SUITE_PLAN.values() for p in probes]
ANSWER_KEY = answer_key(ALL_PROBES)
# cell -> correct answer, for BENCH. Public benchmark answers, which BENCH
# legitimately has; nothing else here sees them.
BENCH_KEY = {p.cell: p.answer for p in suite("bench") if p.answer}


def queries_per_session() -> int:
    return sum(len(p) * r for p, r in SUITE_PLAN.values())


def build_auditors(*, iris_trees: int = 100, iris_splits: int = 3,
                   ote_perm: int = 200) -> dict[str, Any]:
    """Fresh auditor instances. Thresholds are attached later, once frozen."""
    return {
        "OTE": OTEAuditor(n_perm=ote_perm),
        "IRIS-lite": IRISAuditor(n_estimators=iris_trees, n_splits=iris_splits),
        "GATEOPS": GateOpsAuditor(),
        "KBF": KBFAuditor(),
        "BENCH": BenchAuditor(answer_key=BENCH_KEY),
        "RUT": RUTAuditor(),
    }


def make_gateway(arm: str, seed: int, ledger_path, arm_cfg=None) -> Gateway:
    """A gateway on a fresh mock session, seeded for reproducible independence."""
    return Gateway(
        MOCK_LADDER, arm,
        MockBackend(session_seed=seed, answer_key=ANSWER_KEY),
        ledger=Ledger(path=ledger_path, prices=load_prices()),
        arm_cfg=arm_cfg if arm_cfg is not None else load_arm_config(),
    )


async def run_session(arm: str, seed: int, ledger_path, arm_cfg=None
                      ) -> dict[str, list[Observation]]:
    """Send every suite through one arm. Returns observations keyed by suite."""
    gw = make_gateway(arm, seed, ledger_path, arm_cfg)
    out: dict[str, list[Observation]] = {}
    for name, (probes, repeats) in SUITE_PLAN.items():
        out[name] = await collect(gw, probes, repeats=repeats)
    return out


def audit_session(
    auditors: dict[str, Any],
    session: dict[str, list[Observation]],
    reference: dict[str, list[Observation]],
    *,
    prices: dict[str, Any] | None = None,
    alpha: float = 0.01,
) -> dict[str, AuditResult]:
    """Score one session against a reference. Returns per-auditor results + FUSE."""
    results: dict[str, AuditResult] = {}
    for name, auditor in auditors.items():
        s = AUDITOR_SUITE[name]
        results[name] = auditor.audit(
            session.get(s, []), reference.get(s, []),
            cost_usd=audit_cost(session.get(s, []), prices or {}),
        )

    # FUSE consumes the others, so it must not be in `auditors` itself.
    results["FUSE"] = fuse(results, alpha=alpha)
    return results


def audit_cost(obs: Sequence[Observation], prices: dict[str, Any]) -> float:
    """What these probes WOULD cost the auditor on a paid tier.

    Priced at the ADVERTISED model's rate, not the true backend's. The auditor
    pays for what it was sold regardless of what it received - which is the
    entire grievance the project is about, and the correct input to the
    break-even analysis.
    """
    entry = prices.get(f"mock:{MOCK_LADDER.advertised}")
    if not entry:
        return 0.0
    p_in = float(entry.get("input_per_mtok", 0.0))
    p_out = float(entry.get("output_per_mtok", 0.0))
    tin = sum(float((o.usage or {}).get("prompt_tokens") or 0) for o in obs)
    tout = sum(float((o.usage or {}).get("completion_tokens") or 0) for o in obs)
    return (tin * p_in + tout * p_out) / 1_000_000.0
