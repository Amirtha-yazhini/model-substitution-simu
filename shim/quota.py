"""Per-provider rate limiting and daily quota accounting.

Free tiers meter on two independent axes and both will bite:
  - requests per minute  -> token bucket, enforced by waiting
  - requests per day     -> hard counter, enforced by refusing

The daily counter persists to disk keyed by UTC date, so restarting the census
does not silently reset a budget that the provider is still counting. OpenRouter
at 50 requests/day account-wide is the binding case; burning it accidentally
costs the A11 arm its entire day.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "results" / "quota_state.json"


class QuotaExhausted(RuntimeError):
    """Raised when a provider's daily budget is spent."""

    def __init__(self, provider: str, used: int, cap: int):
        super().__init__(f"{provider}: daily quota exhausted ({used}/{cap})")
        self.provider = provider
        self.used = used
        self.cap = cap


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class ProviderBudget:
    name: str
    rpm: int | None = None
    rpd: int | None = None
    reserve: int = 0          # requests held back from the daily cap
    used_today: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _next_free: float = 0.0   # monotonic timestamp of next allowed send

    @property
    def spendable(self) -> int | None:
        if self.rpd is None:
            return None
        return max(self.rpd - self.reserve, 0)

    @property
    def remaining(self) -> int | None:
        cap = self.spendable
        return None if cap is None else max(cap - self.used_today, 0)


class QuotaManager:
    """Gate every outbound call through acquire()."""

    def __init__(self, budgets: dict[str, ProviderBudget], *, persist: bool = True,
                 rpm_margin: float = 0.85):
        self.budgets = budgets
        self.persist = persist
        # Pace below the documented rate, not exactly at it. Spacing requests at
        # exactly 60/RPM puts every request on the limit boundary, where clock
        # skew and the provider's own windowing produce 429s at a steady rate -
        # which is what cost the first census run about half its sample. The
        # margin is far cheaper than the retries it avoids.
        self.rpm_margin = rpm_margin
        self._date = _today()
        if persist:
            self._load()

    # ---------- persistence ----------

    def _load(self) -> None:
        if not STATE_PATH.exists():
            return
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        if state.get("date") != self._date:
            return  # stale day: counters correctly start at zero
        for name, used in (state.get("used") or {}).items():
            if name in self.budgets:
                self.budgets[name].used_today = int(used)

    def _save(self) -> None:
        if not self.persist:
            return
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(
                {
                    "date": self._date,
                    "used": {n: b.used_today for n, b in self.budgets.items()},
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _roll_day(self) -> None:
        today = _today()
        if today != self._date:
            self._date = today
            for b in self.budgets.values():
                b.used_today = 0
            self._save()

    # ---------- gating ----------

    async def acquire(self, provider: str) -> None:
        """Wait for an RPM slot and consume one unit of daily budget."""
        self._roll_day()
        b = self.budgets.get(provider)
        if b is None:
            return  # unmetered / unknown provider

        async with b._lock:
            remaining = b.remaining
            if remaining is not None and remaining <= 0:
                raise QuotaExhausted(provider, b.used_today, b.spendable or 0)

            if b.rpm:
                interval = 60.0 / (float(b.rpm) * self.rpm_margin)
                now = time.monotonic()
                wait = b._next_free - now
                if wait > 0:
                    await asyncio.sleep(wait)
                    now = time.monotonic()
                b._next_free = max(now, b._next_free) + interval

            b.used_today += 1
            self._save()

    def can_serve(self, provider: str) -> bool:
        self._roll_day()
        b = self.budgets.get(provider)
        if b is None:
            return True
        r = b.remaining
        return r is None or r > 0

    def refund(self, provider: str) -> None:
        """Give back a unit when a call failed before the provider metered it."""
        b = self.budgets.get(provider)
        if b and b.used_today > 0:
            b.used_today -= 1
            self._save()

    def report(self) -> str:
        self._roll_day()
        lines = [f"quota @ {self._date} (UTC)"]
        for name, b in sorted(self.budgets.items()):
            cap = b.spendable
            if cap is None:
                lines.append(f"  {name:<12} {b.used_today} used (no daily cap)")
            else:
                lines.append(
                    f"  {name:<12} {b.used_today}/{cap} used, {b.remaining} left"
                    + (f" (+{b.reserve} reserved)" if b.reserve else "")
                )
        return "\n".join(lines)


def budgets_from_providers(providers: dict, reserves: dict[str, int] | None = None) -> dict[str, ProviderBudget]:
    """Build budgets from config/providers.yaml, preferring measured limits."""
    reserves = reserves or {}
    out: dict[str, ProviderBudget] = {}
    for name, p in providers.items():
        meta = getattr(p, "meta", {}) or {}
        out[name] = ProviderBudget(
            name=name,
            rpm=meta.get("measured_rpm") or meta.get("documented_rpm"),
            rpd=meta.get("measured_rpd") or meta.get("documented_rpd"),
            reserve=reserves.get(name, 0),
        )
    return out
