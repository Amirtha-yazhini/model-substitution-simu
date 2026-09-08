"""Thin async client for OpenAI-compatible free-tier endpoints.

Deliberately minimal: no SDK, no retries-by-magic. We need exact visibility into
what the wire actually returned (status codes, missing usage fields, latency)
because those observations ARE the coverage measurement, not incidental plumbing.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass
class Provider:
    name: str
    base_url: str
    env_key: str
    auth: str = "bearer"
    openai_compatible: str | bool = True
    role: str = "unspecified"
    enabled: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def api_key(self) -> str | None:
        key = os.getenv(self.env_key)
        return key.strip() if key and key.strip() else None

    @property
    def configured(self) -> bool:
        return self.api_key is not None

    def headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if self.name == "openrouter":
            # OpenRouter asks for attribution headers; harmless elsewhere.
            h["HTTP-Referer"] = "https://github.com/local/model-substitution-simu"
            h["X-Title"] = "SHIM auditor benchmark"
        return h


@dataclass
class CallResult:
    """One request/response, including the failure modes we care about."""

    ok: bool
    status: int | None
    latency_s: float
    text: str | None = None
    raw: dict[str, Any] | None = None
    error: str | None = None

    # capability observations - these feed the coverage table
    usage: dict[str, Any] | None = None
    has_logprobs: bool = False
    system_fingerprint: str | None = None
    finish_reason: str | None = None

    @property
    def rate_limited(self) -> bool:
        return self.status == 429


def load_providers(path: Path | None = None) -> dict[str, Provider]:
    path = path or ROOT / "config" / "providers.yaml"
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    out: dict[str, Provider] = {}
    for name, spec in cfg.get("providers", {}).items():
        out[name] = Provider(
            name=name,
            base_url=spec["base_url"].rstrip("/"),
            env_key=spec["env_key"],
            auth=spec.get("auth", "bearer"),
            openai_compatible=spec.get("openai_compatible", True),
            role=spec.get("role", "unspecified"),
            enabled=spec.get("enabled", True),
            meta=spec,
        )
    return out


class Client:
    """One httpx client, reused across providers."""

    def __init__(self, timeout: float = 60.0):
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "Client":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def list_models(self, provider: Provider) -> tuple[list[str], str | None]:
        """GET /models. Returns (slugs, error). Not all providers implement it."""
        url = f"{provider.base_url}/models"
        try:
            r = await self._client.get(url, headers=provider.headers())
        except Exception as exc:  # noqa: BLE001 - we want the message verbatim
            return [], f"{type(exc).__name__}: {exc}"

        if r.status_code != 200:
            return [], f"HTTP {r.status_code}: {r.text[:200]}"

        try:
            body = r.json()
        except Exception as exc:  # noqa: BLE001
            return [], f"unparseable JSON: {exc}"

        data = body.get("data", body if isinstance(body, list) else [])
        slugs = []
        for item in data:
            if isinstance(item, dict):
                slug = item.get("id") or item.get("name")
                if slug:
                    slugs.append(str(slug))
        return sorted(slugs), None

    async def chat(
        self,
        provider: Provider,
        model: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 16,
        temperature: float | None = None,
        top_p: float | None = None,
        logprobs: bool = False,
        top_logprobs: int | None = None,
        seed: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> CallResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if logprobs:
            payload["logprobs"] = True
            if top_logprobs is not None:
                payload["top_logprobs"] = top_logprobs
        if seed is not None:
            payload["seed"] = seed
        if extra:
            payload.update(extra)

        url = f"{provider.base_url}/chat/completions"
        t0 = time.perf_counter()
        try:
            r = await self._client.post(url, headers=provider.headers(), json=payload)
        except Exception as exc:  # noqa: BLE001
            return CallResult(
                ok=False,
                status=None,
                latency_s=time.perf_counter() - t0,
                error=f"{type(exc).__name__}: {exc}",
            )
        latency = time.perf_counter() - t0

        if r.status_code != 200:
            return CallResult(
                ok=False,
                status=r.status_code,
                latency_s=latency,
                error=r.text[:400],
            )

        try:
            body = r.json()
        except Exception as exc:  # noqa: BLE001
            return CallResult(
                ok=False, status=r.status_code, latency_s=latency,
                error=f"unparseable JSON: {exc}",
            )

        choices = body.get("choices") or []
        choice = choices[0] if choices else {}
        message = choice.get("message") or {}
        text = message.get("content")

        return CallResult(
            ok=True,
            status=r.status_code,
            latency_s=latency,
            text=text,
            raw=body,
            usage=body.get("usage"),
            has_logprobs=bool(choice.get("logprobs")),
            system_fingerprint=body.get("system_fingerprint"),
            finish_reason=choice.get("finish_reason"),
        )
