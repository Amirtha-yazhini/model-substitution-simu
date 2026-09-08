"""The auditor interface every method implements.

One type carries the lesson of the 2026 frozen-threshold holdout study
(arXiv:2608.29930): a method that CANNOT RUN must not be scored as though it
passed. That study found only 6 of 12 holdout pairs were even scoreable, and
counting the unscoreable ones as agreement would have inflated its numbers.
Here `applicable=False` forces the decision to "uninformative", never
"consistent" - the distinction is enforced by the type, not by discipline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

Decision = Literal["consistent", "inconsistent", "uninformative"]


@dataclass
class Observation:
    """One probe response, as an auditor sees it.

    This is deliberately the CLIENT's view: no true backend, no ground-truth
    label. Auditors must not be able to cheat by reading the ledger.
    """

    probe_id: str
    cell: str                      # probe family/cell, e.g. "rand100.en"
    text: str | None
    latency_s: float
    usage: dict[str, Any] = field(default_factory=dict)
    system_fingerprint: str | None = None
    finish_reason: str | None = None
    logprobs: Any | None = None
    ok: bool = True

    @property
    def answer(self) -> str:
        return (self.text or "").strip()


@dataclass
class AuditResult:
    decision: Decision
    score: float                   # calibrated; higher = more suspicious
    e_value: float = 1.0           # for anytime-valid sequential stopping
    queries: int = 0
    cost_usd: float = 0.0
    applicable: bool = True
    channel_scores: dict[str, float] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def uninformative(cls, reason: str, *, queries: int = 0, cost_usd: float = 0.0) -> "AuditResult":
        """The correct output when a method cannot run. NOT a pass."""
        return cls(
            decision="uninformative", score=float("nan"), e_value=1.0,
            queries=queries, cost_usd=cost_usd, applicable=False,
            detail={"reason": reason},
        )


class Auditor(ABC):
    """Base class. Subclasses implement `score` and declare their requirements."""

    name: str = "unnamed"
    paper: str = ""
    # Capability requirements, checked against the measured coverage table.
    requires_logprobs: bool = False
    requires_cached_tokens: bool = False
    requires_reference: bool = True

    def __init__(self, threshold: float | None = None, **kw: Any):
        self.threshold = threshold
        self.config = kw

    # ------------------------------------------------------------------

    def check_applicable(self, suspect: Sequence[Observation],
                         reference: Sequence[Observation] | None) -> str | None:
        """Return a reason string if this auditor cannot run, else None."""
        if not suspect:
            return "no suspect observations"
        if self.requires_reference and not reference:
            return "no reference observations available"
        if self.requires_logprobs and not any(o.logprobs for o in suspect):
            return "endpoint does not expose logprobs"
        if self.requires_cached_tokens and not any(
            "cached_tokens" in (o.usage or {}) for o in suspect
        ):
            return "endpoint does not report usage.cached_tokens"
        return None

    @abstractmethod
    def score(self, suspect: Sequence[Observation],
              reference: Sequence[Observation] | None) -> tuple[float, dict[str, Any]]:
        """Return (suspicion score, detail). Higher = more suspicious."""

    # ------------------------------------------------------------------

    def audit(
        self,
        suspect: Sequence[Observation],
        reference: Sequence[Observation] | None = None,
        *,
        cost_usd: float = 0.0,
    ) -> AuditResult:
        reason = self.check_applicable(suspect, reference)
        if reason:
            return AuditResult.uninformative(reason, queries=len(suspect), cost_usd=cost_usd)

        raw, detail = self.score(suspect, reference)
        if raw != raw:  # NaN
            return AuditResult.uninformative(
                detail.get("reason", "score undefined"),
                queries=len(suspect), cost_usd=cost_usd,
            )

        decision: Decision = "uninformative"
        if self.threshold is not None:
            decision = "inconsistent" if raw >= self.threshold else "consistent"

        return AuditResult(
            decision=decision, score=raw, queries=len(suspect),
            cost_usd=cost_usd, applicable=True, detail=detail,
        )


def group_by_cell(obs: Sequence[Observation]) -> dict[str, list[Observation]]:
    out: dict[str, list[Observation]] = {}
    for o in obs:
        out.setdefault(o.cell, []).append(o)
    return out
