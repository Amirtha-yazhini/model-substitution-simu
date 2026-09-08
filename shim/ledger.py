"""Append-only record of what SHIM actually did.

One JSONL line per request. This file is the ground truth for every metric in the
project: it holds the true backend behind each response, which the client never
sees. Without it there are no ROC curves, because there are no labels.

It also carries imputed cost. We never spend money, so dollars are computed from
published price tables applied to measured token counts - which is all the
economics analysis (idea.md C3a) needs.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import BackendResponse, RoutingDecision, canonical_hash

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "results" / "ledger.jsonl"


class Ledger:
    def __init__(self, path: Path | None = None, prices: dict[str, Any] | None = None):
        self.path = path or DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.prices = prices or {}
        self._lock = threading.Lock()
        self._n = 0

    def impute_cost(self, endpoint_key: str, usage: dict[str, Any]) -> float | None:
        """Cost this request WOULD have had on paid tiers, per published rates."""
        entry = self.prices.get(endpoint_key)
        if not entry:
            return None
        p_in = float(entry.get("input_per_mtok", 0.0))
        p_out = float(entry.get("output_per_mtok", 0.0))
        n_in = float(usage.get("prompt_tokens") or 0)
        n_out = float(usage.get("completion_tokens") or 0)
        return (n_in * p_in + n_out * p_out) / 1_000_000.0

    def record(
        self,
        *,
        arm: str,
        advertised_model: str,
        decision: RoutingDecision,
        response: BackendResponse,
        request_hash: str,
        reported_usage: dict[str, Any] | None,
        wall_latency_s: float,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        true_usage = response.usage
        endpoint_key = str(decision.endpoint)

        row: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "arm": arm,
            "advertised_model": advertised_model,
            # --- ground truth: never visible to the client ---
            "true_provider": decision.endpoint.provider,
            "true_model": decision.endpoint.model,
            "is_genuine": decision.is_genuine,
            "routing_reason": decision.reason,
            # --- what the client can see ---
            "request_hash": request_hash,
            "response_hash": canonical_hash(response.text or ""),
            "response_text": response.text,
            "ok": response.ok,
            "error": response.error,
            "from_cache": response.from_cache,
            "wall_latency_s": round(wall_latency_s, 4),
            "backend_latency_s": round(response.latency_s, 4),
            "injected_latency_s": round(decision.inject_latency_s, 4),
            "reported_usage": reported_usage,
            "true_usage": true_usage,
            "imputed_cost_usd": self.impute_cost(endpoint_key, true_usage),
            # --- manipulations applied ---
            "usage_multiplier": decision.usage_multiplier,
            "laundered": decision.launder,
            "override_temperature": decision.override_temperature,
        }
        if extra:
            row.update(extra)

        line = json.dumps(row, ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            self._n += 1
        return row

    @property
    def count(self) -> int:
        return self._n


def load_prices(path: Path | None = None) -> dict[str, Any]:
    import yaml

    path = path or ROOT / "config" / "prices.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return cfg.get("endpoints", {}) or {}
