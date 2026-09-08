"""The 12 adversary arms (A0-A11).

Each Policy answers one question: given this inbound request, where does it go and
what gets done to the response? Policies are PURE with respect to routing - they
take an AuditRequest and return a RoutingDecision - which makes every arm testable
without a network.

Determinism matters. A3 and A11 seed their randomness on a hash of the request
body, never on wall-clock time, so replaying an audit reproduces identical routing.
Otherwise two auditors "evaluated on the same arm" would in fact face two different
random realisations of it, and the comparison would be meaningless.
"""

from __future__ import annotations

import hashlib
import math
import random
from abc import ABC, abstractmethod
from collections import Counter
from pathlib import Path
from typing import Any

from .types import AuditRequest, Endpoint, Ladder, RoutingDecision

ROOT = Path(__file__).resolve().parent.parent


def _unit_from_hash(body_hash: str, salt: str = "") -> float:
    """Map a request hash to a deterministic uniform draw in [0, 1)."""
    h = hashlib.sha256((salt + body_hash).encode("utf-8")).hexdigest()
    return int(h[:16], 16) / float(1 << 64)


class Policy(ABC):
    arm: str = "A?"
    name: str = "unnamed"

    def __init__(self, ladder: Ladder, cfg: dict[str, Any] | None = None):
        self.ladder = ladder
        self.cfg = cfg or {}

    @abstractmethod
    def route(self, req: AuditRequest) -> RoutingDecision: ...

    # helpers -------------------------------------------------------------

    def _genuine(self, reason: str, **kw: Any) -> RoutingDecision:
        return RoutingDecision(
            endpoint=self.ladder.genuine, is_genuine=True,
            arm=self.arm, reason=reason, **kw,
        )

    def _substitute(self, reason: str, **kw: Any) -> RoutingDecision:
        return RoutingDecision(
            endpoint=self.ladder.substitute, is_genuine=False,
            arm=self.arm, reason=reason, **kw,
        )


# --------------------------------------------------------------------------
# A0-A4: reproduce the literature's own threat models
# --------------------------------------------------------------------------

class HonestPolicy(Policy):
    arm, name = "A0", "honest"

    def route(self, req: AuditRequest) -> RoutingDecision:
        return self._genuine("advertised model served")


class FullSubstitutionPolicy(Policy):
    arm, name = "A1", "full_substitution"

    def route(self, req: AuditRequest) -> RoutingDecision:
        return self._substitute("always substitute")


class QuantizationSwapPolicy(Policy):
    """Same nominal model, different provider - likely different precision.

    Labelled genuine=False: the weights are nominally correct but the numerics may
    not be, and the client's expectation of a specific deployment is broken. This
    is the most debatable label in the taxonomy, so it is configurable.
    """

    arm, name = "A2", "quantization_swap"

    def route(self, req: AuditRequest) -> RoutingDecision:
        target = self.ladder.alternates[0] if self.ladder.alternates else self.ladder.substitute
        genuine = bool(self.cfg.get("label_as_genuine", False))
        return RoutingDecision(
            endpoint=target, is_genuine=genuine, arm=self.arm,
            reason=f"alternate provider {target.provider}",
        )


class DilutionPolicy(Policy):
    """Serve the substitute on a fraction eps of requests.

    The mixture this creates is what makes detection hard: the observed
    distribution is (1-eps)*P_genuine + eps*P_substitute, which converges to
    P_genuine as eps shrinks. Hence IRIS's Theta(1/eps) / Theta(1/eps^2) query
    complexity, and hence the break-even eps* in the economics analysis.
    """

    arm, name = "A3", "dilution"

    def route(self, req: AuditRequest) -> RoutingDecision:
        eps = float(self.cfg.get("eps", 0.10))
        draw = _unit_from_hash(req.body_hash, salt="A3")
        if draw < eps:
            return self._substitute(f"diluted (eps={eps}, draw={draw:.4f})")
        return self._genuine(f"not diluted (eps={eps}, draw={draw:.4f})")


class SamplerRetunePolicy(Policy):
    """Genuine weights, silently altered sampling parameters.

    genuine=True on purpose. If a distribution-based auditor flags this as
    substitution it has confused "the distribution moved" with "the model changed",
    which is a specificity failure worth reporting. IRIS explicitly calls this
    out-of-scope, meaning nobody has tested whether their detector over-fires here.
    """

    arm, name = "A4", "sampler_retune"

    def route(self, req: AuditRequest) -> RoutingDecision:
        return self._genuine(
            "genuine weights, sampler overridden",
            override_temperature=self.cfg.get("override_temperature"),
            override_top_p=self.cfg.get("override_top_p"),
        )


# --------------------------------------------------------------------------
# A5-A10: the evasive adversary. No source paper evaluates against these.
# --------------------------------------------------------------------------

class ProbeAwareEvasionPolicy(Policy):
    """Generalisation-based evasion: classify request SHAPE, not content.

    Substitutes by default, but serves the genuine model to anything that looks
    like an audit probe. Because it reasons about shape (length, max_tokens,
    closed answer space, repetition) it catches probes it has never seen - which
    is exactly what makes it harder to escape than A10's static lookup.

    Over-triggering is cheap for the adversary: a false positive just means an
    ordinary short query also gets honest treatment. No detection risk.
    """

    arm, name = "A5", "probe_aware_evasion"

    def __init__(self, ladder: Ladder, cfg: dict[str, Any] | None = None):
        super().__init__(ladder, cfg)
        self._seen: Counter[str] = Counter()
        d = (self.cfg.get("detector") or {})
        self.max_tokens_at_most = int(d.get("max_tokens_at_most", 24))
        self.prompt_chars_at_most = int(d.get("prompt_chars_at_most", 220))
        self.repeat_threshold = int(d.get("repeat_threshold", 2))
        self.markers = [m.lower() for m in (d.get("closed_answer_markers") or [])]

    def looks_like_probe(self, req: AuditRequest) -> tuple[bool, str]:
        prompt = req.prompt_text
        key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        self._seen[key] += 1
        seen = self._seen[key]

        signals = []
        if req.max_tokens and req.max_tokens <= self.max_tokens_at_most:
            signals.append(f"max_tokens<={self.max_tokens_at_most}")
        if len(prompt) <= self.prompt_chars_at_most:
            signals.append("short prompt")
        if seen >= self.repeat_threshold:
            signals.append(f"repeat #{seen}")
        low = prompt.lower()
        for m in self.markers:
            if m in low:
                signals.append(f"closed-answer marker '{m}'")
                break

        # Two independent signals is enough - a real gateway would tune this,
        # and being slightly trigger-happy costs the adversary nothing.
        return (len(signals) >= 2, ", ".join(signals) or "no signals")

    def route(self, req: AuditRequest) -> RoutingDecision:
        is_probe, why = self.looks_like_probe(req)
        if is_probe:
            return self._genuine(f"EVADED: probe-shaped ({why})")
        return self._substitute(f"substituted: not probe-shaped ({why})")


class CacheReplayPolicy(Policy):
    """Serve a memoised completion for a repeated prompt.

    Breaks every auditor that estimates an output DISTRIBUTION by sending the same
    probe many times - the "distribution" collected becomes an artefact of the
    cache, not of the model.
    """

    arm, name = "A6", "cache_replay"

    def __init__(self, ladder: Ladder, cfg: dict[str, Any] | None = None):
        super().__init__(ladder, cfg)
        self._cache: dict[str, Any] = {}

    def cache_key(self, req: AuditRequest) -> str:
        return hashlib.sha256(
            f"{req.model}|{req.prompt_text}|{req.max_tokens}".encode("utf-8")
        ).hexdigest()

    def route(self, req: AuditRequest) -> RoutingDecision:
        key = self.cache_key(req)
        underlying = self.cfg.get("underlying", "substitute")
        base = self._substitute if underlying == "substitute" else self._genuine
        if key in self._cache:
            return base("cache hit - replaying stored completion", serve_from_cache=True)
        return base("cache miss - will store")

    def cache_get(self, req: AuditRequest) -> Any | None:
        return self._cache.get(self.cache_key(req))

    def cache_put(self, req: AuditRequest, body: Any) -> None:
        self._cache[self.cache_key(req)] = body


class LaunderingPolicy(Policy):
    """Cheap model generates; a second pass restyles to match the target's surface.

    Targets IRIS-lite specifically: its features are format-compliance,
    symbol-frequency, transition, run-structure and positional-balance statistics -
    all properties of the visible string, all imitable by a restyling pass that
    never touches semantics.
    """

    arm, name = "A7", "laundering"

    def route(self, req: AuditRequest) -> RoutingDecision:
        # Default: the cheap model does both hops. That is the realistic attack -
        # paying the expensive model to launder would defeat the point of the
        # substitution - and it is what makes A7 cost 2 calls per request.
        via_model = self.cfg.get("via_model")
        via = (
            Endpoint(self.ladder.substitute.provider, via_model)
            if via_model else self.ladder.substitute
        )
        return self._substitute(
            f"substituted then laundered via {via}",
            launder=True, launder_via=via,
            launder_max_tokens=int(self.cfg.get("launder_max_tokens", 256)),
        )


class BillingManipulationPolicy(Policy):
    arm, name = "A8", "billing_manipulation"

    def route(self, req: AuditRequest) -> RoutingDecision:
        underlying = self.cfg.get("underlying", "substitute")
        base = self._substitute if underlying == "substitute" else self._genuine
        return base(
            "usage misreported",
            usage_multiplier=float(self.cfg.get("usage_multiplier", 1.25)),
            fake_cached_tokens=self.cfg.get("fake_cached_tokens"),
        )


class LatencyShapingPolicy(Policy):
    """Inject jitter so the mixture mimics one homogeneous backend.

    Targets GateScope's CV = sigma/mu metric. Note it shapes toward a REALISTIC
    profile rather than flattening variance to zero: an implausibly low CV is
    itself a tell, and GateScope's own baseline was ~0.63, not 0.

    Unlike every other arm, this one COSTS the adversary something - the substitute
    is usually faster, so hiding means throwing away the speed advantage.
    """

    arm, name = "A9", "latency_shaping"

    def route(self, req: AuditRequest) -> RoutingDecision:
        underlying = self.cfg.get("underlying", "substitute")
        base = self._substitute if underlying == "substitute" else self._genuine

        target_mean = float(self.cfg.get("target_mean_s", 0.9))
        target_cv = float(self.cfg.get("target_cv", 0.63))

        # Lognormal: positive support and right skew, like real serving latency.
        # Solving for (mu, sigma) that give exactly this mean and CV.
        sigma = math.sqrt(math.log(target_cv ** 2 + 1))
        mu = math.log(max(target_mean, 1e-6)) - 0.5 * sigma ** 2

        seed = int(hashlib.sha256(("A9" + req.body_hash).encode()).hexdigest()[:16], 16)
        rng = random.Random(seed)
        target_total = math.exp(rng.gauss(mu, sigma))

        return base(
            f"latency shaped toward mean={target_mean}s cv={target_cv}",
            inject_latency_s=max(0.0, target_total),
        )


class CanaryAwarePolicy(Policy):
    """Memorisation-based evasion: static lookup against a public corpus.

    Defeats benchmark-based detection (Cai et al.) because MMLU/GPQA/GSM8K are
    public, finite and hashable. Much easier to build than A5 - and much easier
    for an auditor to escape, since any paraphrase slips past an exact match.
    That asymmetry is a predicted result: A10 should be the weakest evasion.
    """

    arm, name = "A10", "canary_aware"

    def __init__(self, ladder: Ladder, cfg: dict[str, Any] | None = None):
        super().__init__(ladder, cfg)
        self.canaries = self._load_canaries()

    def _load_canaries(self) -> list[str]:
        rel = self.cfg.get("canary_file", "config/canaries.txt")
        path = ROOT / rel
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line.lower())
        return out

    def is_canary(self, req: AuditRequest) -> tuple[bool, str]:
        low = req.prompt_text.lower()
        if not low:
            return False, "empty prompt"
        for c in self.canaries:
            if c in low:
                return True, f"matched canary '{c[:48]}...'"
        return False, "no canary match"

    def route(self, req: AuditRequest) -> RoutingDecision:
        hit, why = self.is_canary(req)
        if hit:
            return self._genuine(f"EVADED: {why}")
        return self._substitute(f"substituted: {why}")


# --------------------------------------------------------------------------
# A11: the arm that is not an attack
# --------------------------------------------------------------------------

class BenignRoutingPolicy(Policy):
    """Round-robin among GENUINE providers of the CORRECT model. Not fraud.

    Structurally near-identical to A3 - both split traffic probabilistically
    across backends - but every destination serves the advertised weights. Scored
    as a FALSE-POSITIVE arm: if auditors flag this like they flag A3, then
    client-side auditing cannot distinguish fraud from sanctioned quality routing,
    which is the central claim in idea.md section 5.
    """

    arm, name = "A11", "benign_quality_routing"

    def __init__(self, ladder: Ladder, cfg: dict[str, Any] | None = None):
        super().__init__(ladder, cfg)
        self.pool: list[Endpoint] = [ladder.genuine, *ladder.alternates]
        self._n = 0

    def route(self, req: AuditRequest) -> RoutingDecision:
        # Periodic reweighting, mimicking Auto Exacto's ~5-minute re-evaluation.
        period = int(self.cfg.get("reweight_every", 25))
        epoch = self._n // max(period, 1)
        self._n += 1

        draw = _unit_from_hash(req.body_hash, salt=f"A11e{epoch}")
        idx = int(draw * len(self.pool)) % len(self.pool)
        target = self.pool[idx]

        return RoutingDecision(
            endpoint=target,
            is_genuine=True,  # correct weights everywhere in the pool
            arm=self.arm,
            reason=f"benign route to {target.provider} (epoch {epoch}, pool {len(self.pool)})",
        )


# --------------------------------------------------------------------------

REGISTRY: dict[str, type[Policy]] = {
    "A0": HonestPolicy,
    "A1": FullSubstitutionPolicy,
    "A2": QuantizationSwapPolicy,
    "A3": DilutionPolicy,
    "A4": SamplerRetunePolicy,
    "A5": ProbeAwareEvasionPolicy,
    "A6": CacheReplayPolicy,
    "A7": LaunderingPolicy,
    "A8": BillingManipulationPolicy,
    "A9": LatencyShapingPolicy,
    "A10": CanaryAwarePolicy,
    "A11": BenignRoutingPolicy,
}


def load_arm_config(path: Path | None = None) -> dict[str, dict[str, Any]]:
    import yaml

    path = path or ROOT / "config" / "arms.yaml"
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return cfg.get("arms", {}) or {}


def build_policy(arm: str, ladder: Ladder, arm_cfg: dict[str, Any] | None = None) -> Policy:
    arm = arm.upper()
    if arm not in REGISTRY:
        raise KeyError(f"unknown arm {arm!r}; known: {sorted(REGISTRY)}")
    cfg = (arm_cfg or {}).get(arm, {})
    return REGISTRY[arm](ladder, cfg)
