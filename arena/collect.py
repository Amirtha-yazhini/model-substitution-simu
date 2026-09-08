"""Collect Observations by driving probes through a SHIM gateway.

The auditor only ever sees what a client sees: text, latency, usage headers.
Ground truth stays in the ledger. This module is the boundary that enforces that
separation - if an auditor could read `is_genuine` the whole benchmark would be
meaningless.
"""

from __future__ import annotations

from typing import Any, Sequence

from shim.gateway import Gateway
from shim.types import AuditRequest

from .base import Observation
from .probes.ote_probes import Probe


def _to_request(probe: Probe, model: str, nonce: int) -> AuditRequest:
    messages = [{"role": "user", "content": probe.prompt}]
    raw: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": probe.max_tokens,
        "temperature": probe.temperature,
        # Varies the body hash so per-request routing (A3/A11) actually samples
        # rather than returning one frozen decision for every repeat.
        "_repeat": nonce,
    }
    return AuditRequest(
        model=model, messages=messages, max_tokens=probe.max_tokens,
        temperature=probe.temperature, top_p=None, logprobs=False,
        seed=None, raw=raw,
    )


async def collect(
    gateway: Gateway,
    probes: Sequence[Probe],
    *,
    repeats: int = 30,
    model: str | None = None,
) -> list[Observation]:
    """Run every probe `repeats` times through the gateway."""
    advertised = model or gateway.ladder.advertised
    out: list[Observation] = []

    for probe in probes:
        for r in range(repeats):
            req = _to_request(probe, advertised, r)
            body, row = await gateway.handle(req)

            if body is None:
                out.append(Observation(
                    probe_id=f"{probe.cell}#{r}", cell=probe.cell, text=None,
                    latency_s=row.get("wall_latency_s", 0.0), ok=False,
                ))
                continue

            choice = (body.get("choices") or [{}])[0]
            out.append(Observation(
                probe_id=f"{probe.cell}#{r}",
                cell=probe.cell,
                text=(choice.get("message") or {}).get("content"),
                latency_s=row.get("wall_latency_s", 0.0),
                usage=body.get("usage") or {},
                system_fingerprint=body.get("system_fingerprint"),
                finish_reason=choice.get("finish_reason"),
                logprobs=choice.get("logprobs"),
                ok=True,
            ))
    return out


def imputed_cost(obs: Sequence[Observation], prices: dict[str, Any], endpoint_key: str) -> float:
    """What these probes WOULD have cost on a paid tier."""
    entry = prices.get(endpoint_key)
    if not entry:
        return 0.0
    p_in = float(entry.get("input_per_mtok", 0.0))
    p_out = float(entry.get("output_per_mtok", 0.0))
    tin = sum(float((o.usage or {}).get("prompt_tokens") or 0) for o in obs)
    tout = sum(float((o.usage or {}).get("completion_tokens") or 0) for o in obs)
    return (tin * p_in + tout * p_out) / 1_000_000.0
