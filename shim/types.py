"""Shared types for the SHIM gateway.

The central object is RoutingDecision: it carries both what the gateway DID and
the ground-truth label of what it did. That label never reaches the client - it
goes only to the ledger - but it is what lets ARENA compute real ROC curves.
Real-world audits cannot do this, which is the whole reason the simulator exists.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def canonical_hash(obj: Any) -> str:
    """Stable hash of a request body.

    Used to seed per-request randomness (arms A3/A11) so that replaying an audit
    reproduces the exact same routing decisions. Seeding on wall-clock time would
    make the benchmark irreproducible and the auditor comparison unfair.
    """
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class Endpoint:
    """A concrete place a request can actually go."""

    provider: str
    model: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass
class Ladder:
    """One substitution scenario: what is advertised vs what could be served."""

    name: str
    advertised: str          # the slug clients ask SHIM for
    genuine: Endpoint        # what an honest gateway serves
    substitute: Endpoint     # the cheaper thing a dishonest gateway serves
    alternates: list[Endpoint] = field(default_factory=list)
    # alternates = the SAME nominal model on other providers. Substrate for
    # A2 (quantization swap) and A11 (benign routing). Serving one of these is
    # NOT identity fraud - the weights are right - which is exactly the point.


@dataclass
class AuditRequest:
    """An inbound request, parsed into the fields the arms actually reason about."""

    model: str                       # advertised model the client asked for
    messages: list[dict[str, Any]]
    max_tokens: int
    temperature: float | None
    top_p: float | None
    logprobs: bool
    seed: int | None
    raw: dict[str, Any]

    @property
    def body_hash(self) -> str:
        return canonical_hash(self.raw)

    @property
    def prompt_text(self) -> str:
        """Concatenated user-turn text. Input to the A5 and A10 classifiers."""
        parts = []
        for m in self.messages:
            if m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    parts.append(c)
                elif isinstance(c, list):  # multimodal content blocks
                    parts.extend(
                        b.get("text", "") for b in c if isinstance(b, dict)
                    )
        return "\n".join(parts).strip()


@dataclass
class RoutingDecision:
    """Where the request goes, plus every manipulation applied on the way back.

    `is_genuine` is the ground-truth label. Note it means "the advertised weights
    were served" - an A11 route to a different PROVIDER of the correct model is
    still genuine=True, because no identity violation occurred. That distinction
    is the taxonomy in idea.md section 5, encoded in one boolean.
    """

    endpoint: Endpoint
    is_genuine: bool
    arm: str
    reason: str

    # --- response-side manipulations ---
    override_temperature: float | None = None   # A4
    override_top_p: float | None = None         # A4
    serve_from_cache: bool = False              # A6
    launder: bool = False                       # A7
    launder_via: Endpoint | None = None         # A7
    usage_multiplier: float = 1.0               # A8
    fake_cached_tokens: int | None = None       # A8
    inject_latency_s: float = 0.0               # A9

    def label(self) -> str:
        return "genuine" if self.is_genuine else "substituted"


@dataclass
class BackendResponse:
    """What came back from whichever backend actually served the request."""

    ok: bool
    body: dict[str, Any] | None
    latency_s: float
    endpoint: Endpoint
    error: str | None = None
    from_cache: bool = False

    @property
    def text(self) -> str | None:
        if not self.body:
            return None
        choices = self.body.get("choices") or []
        if not choices:
            return None
        return (choices[0].get("message") or {}).get("content")

    @property
    def usage(self) -> dict[str, Any]:
        return (self.body or {}).get("usage") or {}
