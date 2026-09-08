"""OpenAI-compatible HTTP front end for SHIM.

An auditor points its base_url here and cannot tell this from a real provider
except by its behaviour - which is exactly the experiment. The true backend is
never in the response; it goes only to the ledger.

Run:
    python -m shim.server --arm A3 --ladder mock --port 8000

Then:
    curl http://127.0.0.1:8000/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"genuine-70b","messages":[{"role":"user","content":"hi"}],"max_tokens":16}'
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .gateway import Gateway, LiveBackend, load_ladder
from .ledger import Ledger, load_prices
from .mock import MockBackend
from .policy import load_arm_config
from .quota import QuotaManager, budgets_from_providers
from .types import AuditRequest

ROOT = Path(__file__).resolve().parent.parent


def build_app(
    arm: str = "A0",
    ladder_name: str = "mock",
    *,
    live: bool = False,
    real_sleep: bool = False,
    ledger_path: Path | None = None,
) -> FastAPI:
    ladder = load_ladder(ladder_name)
    arm_cfg = load_arm_config()

    if live:
        from .backends import Client, load_providers

        providers = load_providers()
        quota = QuotaManager(budgets_from_providers(providers))
        backend: Any = LiveBackend(Client(), providers, quota)
    else:
        backend = MockBackend()

    gateway = Gateway(
        ladder, arm, backend,
        ledger=Ledger(path=ledger_path, prices=load_prices()),
        arm_cfg=arm_cfg,
        real_sleep=real_sleep,
    )

    app = FastAPI(title="SHIM", version="0.1.0")
    app.state.gateway = gateway

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "arm": gateway.arm,
            "arm_name": arm_cfg.get(gateway.arm, {}).get("name"),
            "ladder": ladder.name,
            "advertised": ladder.advertised,
            "backend": "live" if live else "mock",
            "requests_served": gateway.ledger.count,
        }

    @app.get("/v1/models")
    async def models() -> dict[str, Any]:
        # Advertise only the slug we claim to serve. A gateway that listed its
        # true backends would give the game away immediately.
        return {
            "object": "list",
            "data": [{"id": ladder.advertised, "object": "model", "owned_by": "shim"}],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": {"message": "invalid JSON body"}}, status_code=400)

        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            return JSONResponse(
                {"error": {"message": "'messages' must be a non-empty list"}}, status_code=400
            )

        req = AuditRequest(
            model=body.get("model") or ladder.advertised,
            messages=messages,
            max_tokens=int(body.get("max_tokens") or 16),
            temperature=body.get("temperature"),
            top_p=body.get("top_p"),
            logprobs=bool(body.get("logprobs")),
            seed=body.get("seed"),
            raw=body,
        )

        client_body, row = await gateway.handle(req)
        if client_body is None:
            return JSONResponse(
                {"error": {"message": row.get("error") or "backend failure",
                           "type": "upstream_error"}},
                status_code=502,
            )
        return JSONResponse(client_body)

    return app


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the SHIM adversarial gateway.")
    ap.add_argument("--arm", default="A0", help="adversary arm A0-A11")
    ap.add_argument("--ladder", default="mock", help="ladder name from config/models.yaml, or 'mock'")
    ap.add_argument("--live", action="store_true", help="use real free-tier providers (spends quota)")
    ap.add_argument("--real-sleep", action="store_true", help="actually sleep for A9 latency shaping")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    import uvicorn

    app = build_app(
        args.arm, args.ladder, live=args.live, real_sleep=args.real_sleep
    )
    cfg = load_arm_config().get(args.arm.upper(), {})
    print(f"SHIM serving arm {args.arm.upper()} ({cfg.get('name', '?')}) "
          f"on {'live' if args.live else 'mock'} backend at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
