"""The gateway engine: policy -> backend -> transforms -> ledger.

Kept separate from server.py so the whole pipeline is testable without HTTP.
Everything the client eventually sees passes through handle(); everything the
client must NOT see (the true backend) goes only to the ledger.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import yaml

from .ledger import Ledger, load_prices
from .mock import MockBackend
from .policy import Policy, build_policy, load_arm_config
from .quota import QuotaExhausted, QuotaManager
from .types import AuditRequest, BackendResponse, Endpoint, Ladder, RoutingDecision

ROOT = Path(__file__).resolve().parent.parent


class LiveBackend:
    """Adapts the httpx Client + QuotaManager to the backend interface."""

    def __init__(self, client, providers: dict, quota: QuotaManager | None = None):
        self.client = client
        self.providers = providers
        self.quota = quota

    async def chat(self, endpoint: Endpoint, payload: dict[str, Any], *, nonce: int = 0) -> BackendResponse:
        provider = self.providers.get(endpoint.provider)
        if provider is None:
            return BackendResponse(False, None, 0.0, endpoint, error=f"unknown provider {endpoint.provider}")

        if self.quota:
            try:
                await self.quota.acquire(endpoint.provider)
            except QuotaExhausted as exc:
                return BackendResponse(False, None, 0.0, endpoint, error=str(exc))

        msgs = payload.get("messages") or []
        result = await self.client.chat(
            provider,
            endpoint.model,
            msgs,
            max_tokens=payload.get("max_tokens", 16),
            temperature=payload.get("temperature"),
            top_p=payload.get("top_p"),
            logprobs=bool(payload.get("logprobs")),
            seed=payload.get("seed"),
        )
        if not result.ok and self.quota and result.status in (None, 401, 404):
            self.quota.refund(endpoint.provider)  # provider never metered it

        return BackendResponse(
            ok=result.ok,
            body=result.raw,
            latency_s=result.latency_s,
            endpoint=endpoint,
            error=result.error,
        )


class Gateway:
    """One configured adversary. Holds a policy, a backend and a ledger."""

    def __init__(
        self,
        ladder: Ladder,
        arm: str,
        backend: Any,
        *,
        ledger: Ledger | None = None,
        arm_cfg: dict[str, Any] | None = None,
        real_sleep: bool = False,
    ):
        self.ladder = ladder
        self.arm = arm.upper()
        self.backend = backend
        self.arm_cfg = arm_cfg if arm_cfg is not None else load_arm_config()
        self.policy: Policy = build_policy(self.arm, ladder, self.arm_cfg)
        self.ledger = ledger or Ledger(prices=load_prices())
        self.real_sleep = real_sleep
        self._nonce = 0

    # ------------------------------------------------------------------

    def _payload_for(self, req: AuditRequest, decision: RoutingDecision) -> dict[str, Any]:
        payload = dict(req.raw)
        payload["model"] = decision.endpoint.model
        if decision.override_temperature is not None:
            payload["temperature"] = decision.override_temperature
        if decision.override_top_p is not None:
            payload["top_p"] = decision.override_top_p
        return payload

    def _apply_response_transforms(
        self, body: dict[str, Any], decision: RoutingDecision, advertised: str
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Rewrite what the client sees. Returns (client_body, reported_usage)."""
        out = dict(body)

        # A gateway that leaked the true model name would be caught instantly,
        # so SHIM always echoes the advertised slug. This is the core deception.
        out["model"] = advertised

        usage = dict(out.get("usage") or {})
        if decision.usage_multiplier and decision.usage_multiplier != 1.0:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if isinstance(usage.get(k), (int, float)):
                    usage[k] = int(round(usage[k] * decision.usage_multiplier))
        if decision.fake_cached_tokens is not None:
            usage["cached_tokens"] = int(decision.fake_cached_tokens)
        if usage:
            out["usage"] = usage

        return out, (usage or None)

    async def _launder(
        self, body: dict[str, Any], decision: RoutingDecision
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """A7: restyle the substitute's output to match the target's surface.

        Deliberately a SURFACE operation - the second pass never regenerates the
        answer, only its presentation. That is precisely the attack surface
        IRIS-lite's visible-string features expose: a laundered response should
        keep the CHEAP model's answers while wearing the EXPENSIVE model's
        formatting habits.

        Returns (rewritten body, ledger metadata). The metadata matters: this is
        the only arm that costs the adversary a second call, and the economics
        analysis has to charge them for it.
        """
        target = self.ladder.genuine
        via = decision.launder_via or self.ladder.substitute
        choices = body.get("choices") or []
        if not choices:
            return body, {"launder_calls": 0, "launder_ok": False}

        text = (choices[0].get("message") or {}).get("content") or ""
        # The style target is named in the prompt: an adversary imitating a model
        # obviously knows which model it is imitating.
        restyle_prompt = [{
            "role": "user",
            "content": (
                f"Restyle in the surface style of {target.model}. "
                f"Do not change meaning: {text}"
            ),
        }]
        laundered = await self.backend.chat(
            via,
            {"messages": restyle_prompt, "max_tokens": decision.launder_max_tokens},
            nonce=self._nonce,
        )

        meta: dict[str, Any] = {
            "launder_calls": 1,
            "launder_via": str(via),
            "launder_ok": bool(laundered.ok and laundered.text),
            "launder_latency_s": round(laundered.latency_s, 4),
            "launder_usage": laundered.usage or None,
            "launder_cost_usd": self.ledger.impute_cost(str(via), laundered.usage or {}),
        }

        if not (laundered.ok and laundered.text):
            # Failure is visible rather than silent: an unlaundered response is
            # still a substituted one, and the ledger must say the pass did not
            # run so the arm is not credited with an evasion it never performed.
            return body, meta

        out = dict(body)
        new_choices = [dict(c) for c in choices]
        msg = dict(new_choices[0].get("message") or {})
        msg["content"] = laundered.text
        new_choices[0]["message"] = msg
        out["choices"] = new_choices
        return out, meta

    # ------------------------------------------------------------------

    async def handle(self, req: AuditRequest) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Serve one request. Returns (client_visible_body, ledger_row)."""
        t0 = time.perf_counter()
        self._nonce += 1
        decision = self.policy.route(req)

        # A6: a cache hit never reaches a backend at all.
        cached_body = None
        if decision.serve_from_cache and hasattr(self.policy, "cache_get"):
            cached_body = self.policy.cache_get(req)

        if cached_body is not None:
            response = BackendResponse(
                ok=True, body=cached_body, latency_s=0.0,
                endpoint=decision.endpoint, from_cache=True,
            )
        else:
            payload = self._payload_for(req, decision)
            response = await self.backend.chat(decision.endpoint, payload, nonce=self._nonce)
            if response.ok and response.body is not None and hasattr(self.policy, "cache_put"):
                self.policy.cache_put(req, response.body)

        launder_meta: dict[str, Any] = {}
        if response.ok and decision.launder and response.body is not None:
            laundered_body, launder_meta = await self._launder(response.body, decision)
            response = BackendResponse(
                ok=True,
                body=laundered_body,
                # The second hop is real time on the wire. Charging it to the
                # observed latency is what makes A7 visible to GATEOPS at all -
                # laundering buys surface cover and pays for it in round trips.
                latency_s=response.latency_s + float(launder_meta.get("launder_latency_s") or 0.0),
                endpoint=response.endpoint,
            )

        # A9: shape the observed latency.
        if decision.inject_latency_s > 0:
            pad = max(0.0, decision.inject_latency_s - response.latency_s)
            if self.real_sleep and pad > 0:
                await asyncio.sleep(pad)

        client_body: dict[str, Any] | None = None
        reported_usage: dict[str, Any] | None = None
        if response.ok and response.body is not None:
            client_body, reported_usage = self._apply_response_transforms(
                response.body, decision, req.model
            )

        wall = time.perf_counter() - t0
        if decision.inject_latency_s > 0 and not self.real_sleep:
            # Book the shaped latency without actually burning wall-clock, so
            # offline grids stay fast while GATEOPS still sees the right number.
            wall = max(wall, decision.inject_latency_s)

        row = self.ledger.record(
            arm=self.arm,
            advertised_model=req.model,
            decision=decision,
            response=response,
            request_hash=req.body_hash,
            reported_usage=reported_usage,
            wall_latency_s=wall,
            extra=launder_meta or None,
        )
        return client_body, row


# ----------------------------------------------------------------------
# ladder construction
# ----------------------------------------------------------------------

MOCK_LADDER = Ladder(
    name="mock",
    advertised="genuine-70b",
    genuine=Endpoint("mock", "genuine-70b"),
    substitute=Endpoint("mock", "substitute-8b"),
    alternates=[Endpoint("mock", "alternate-70b")],
)


def load_ladder(name: str, path: Path | None = None) -> Ladder:
    """Build a Ladder from config/models.yaml, preferring resolved slugs."""
    if name == "mock":
        return MOCK_LADDER

    path = path or ROOT / "config" / "models.yaml"
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    spec = (cfg.get("ladders") or {}).get(name)
    if spec is None:
        raise KeyError(f"unknown ladder {name!r}")

    resolved_path = ROOT / "config" / "models.resolved.yaml"
    working: dict[str, list[str]] = {}
    if resolved_path.exists():
        rc = yaml.safe_load(resolved_path.read_text(encoding="utf-8")) or {}
        working = rc.get("working_models", {}) or {}

    def pick(cands: list[dict[str, str]]) -> Endpoint:
        for c in cands:
            prov, slug = c["provider"], c["slug"]
            if not working or slug in working.get(prov, []):
                return Endpoint(prov, slug)
        c = cands[0]
        return Endpoint(c["provider"], c["slug"])

    genuine = pick(spec["genuine"]["candidates"])
    substitute = pick(spec["substitute"]["candidates"])
    alternates = [
        Endpoint(c["provider"], c["slug"])
        for c in spec["genuine"]["candidates"]
        if not (c["provider"] == genuine.provider and c["slug"] == genuine.model)
    ]
    return Ladder(
        name=name, advertised=genuine.model,
        genuine=genuine, substitute=substitute, alternates=alternates,
    )


def make_mock_gateway(arm: str, **kw: Any) -> Gateway:
    return Gateway(MOCK_LADDER, arm, MockBackend(), **kw)
