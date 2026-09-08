"""Record the probe census into the replay corpus.

This is the run that costs real quota, and it is the only one that does. Every
later phase - calibration, the frozen-threshold grid, the figures - replays what
this writes, so the fleet is pinned to a single instant and the evaluation can be
re-run any number of times for free.

Quota arithmetic drives the whole design. Bruckner's full battery is 40 cells x 30
repeats = 1,200 requests per model; at ~3,000 requests/day across the entire free
fleet that is two models. So we run his own documented 8-cell operating point
(EER 10.6% vs 7.3% for the full 40) at 240 requests/model, which fits ~12 models
in a day. That is a cited operating point, not a compromise invented here.

Safety rails, in order of how likely each is to save the day:
  * dry run by default - prints the request budget per provider and fires nothing
  * refuses outright when a provider's plan exceeds its measured daily cap
  * resumes from the corpus, so an interrupted run re-probes only what is missing
  * stops a provider on quota exhaustion instead of grinding through 429s
  * records failures as records - they are the coverage metric, not noise

    python scripts/04_census.py                 # plan only
    python scripts/04_census.py --mock --yes    # no keys, no quota: the self-test corpus
    python scripts/04_census.py --yes           # the real thing
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.corpus import CorpusWriter, record_key  # noqa: E402
from arena.probes.ote_probes import Probe, probe_set  # noqa: E402
from shim.gateway import LiveBackend  # noqa: E402
from shim.mock import MOCK_MODELS, MockBackend  # noqa: E402
from shim.quota import QuotaManager, budgets_from_providers  # noqa: E402
from shim.types import Endpoint  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SUITE = "ote"


def load_roster(mock: bool, only: list[str] | None) -> list[tuple[str, str]]:
    """The endpoints to census, as (provider, model).

    Live roster comes from models.resolved.yaml - the slugs that actually
    ANSWERED during capability probing - never from the candidate list, so the
    census cannot waste quota on models we already measured as dead.
    """
    if mock:
        pairs = [("mock", m) for m in MOCK_MODELS]
    else:
        path = ROOT / "config" / "models.resolved.yaml"
        if not path.exists():
            print("config/models.resolved.yaml missing - run scripts/01_limits.py --yes first.")
            return []
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        pairs = [
            (prov, slug)
            for prov, slugs in (cfg.get("working_models") or {}).items()
            for slug in slugs
        ]
    if only:
        pairs = [(p, m) for p, m in pairs if p in only or m in only]
    return pairs


def plan(roster: list[tuple[str, str]], probes: list[Probe], repeats: int,
         writer: CorpusWriter, providers: dict[str, Any]) -> tuple[dict[str, int], int]:
    """Requests still needed per provider, after subtracting what is on disk."""
    todo: dict[str, int] = {}
    per_endpoint: dict[tuple[str, str], int] = {}
    for provider, model in roster:
        have = writer.existing_keys(provider, model)
        need = sum(
            1
            for pr in probes
            for r in range(repeats)
            if record_key(provider, model, f"{pr.cell}#{r}", r) not in have
        )
        per_endpoint[(provider, model)] = need
        todo[provider] = todo.get(provider, 0) + need

    print("=" * 76)
    print("Census plan (quota is the scarce resource - review before firing)")
    print("=" * 76)
    print(f"  suite={SUITE}  {len(probes)} cells x {repeats} repeats "
          f"= {len(probes)*repeats} requests per endpoint\n")

    blocked = 0
    for provider in sorted(todo):
        meta = getattr(providers.get(provider), "meta", {}) or {}
        cap = meta.get("measured_rpd") or meta.get("documented_rpd")
        eps = [f"{m} ({n})" for (p, m), n in per_endpoint.items() if p == provider and n]
        done = sum(1 for (p, m), n in per_endpoint.items() if p == provider and not n)
        capstr = f"cap {cap}/day" if cap else "no daily cap"
        over = cap is not None and todo[provider] > cap
        if over:
            blocked += 1
        print(f"  {provider:<12} {todo[provider]:>5} requests  {capstr:<16}"
              f"{'  *** EXCEEDS CAP ***' if over else ''}")
        if eps:
            print(f"               {', '.join(eps)}")
        if done:
            print(f"               ({done} endpoint(s) already complete on disk)")

    total = sum(todo.values())
    print(f"\n  TOTAL: {total} requests")
    return todo, blocked


async def census_endpoint(
    backend: Any, writer: CorpusWriter, provider: str, model: str,
    probes: list[Probe], repeats: int,
) -> dict[str, Any]:
    """Probe one endpoint, skipping anything already recorded."""
    endpoint = Endpoint(provider, model)
    have = writer.existing_keys(provider, model)
    stats = {"endpoint": f"{provider}:{model}", "sent": 0, "ok": 0,
             "failed": 0, "skipped": 0, "stopped": None}

    for probe in probes:
        for r in range(repeats):
            probe_id = f"{probe.cell}#{r}"
            if record_key(provider, model, probe_id, r) in have:
                stats["skipped"] += 1
                continue

            payload = {
                "model": model,
                "messages": [{"role": "user", "content": probe.prompt}],
                "max_tokens": probe.max_tokens,
                "temperature": probe.temperature,
            }
            resp = await backend.chat(endpoint, payload, nonce=r)
            stats["sent"] += 1
            writer.write(
                provider=provider, model=model, suite=SUITE, cell=probe.cell,
                probe_id=probe_id, repeat=r, prompt=probe.prompt,
                max_tokens=probe.max_tokens, temperature=probe.temperature,
                response=resp,
            )
            if resp.ok:
                stats["ok"] += 1
                continue

            stats["failed"] += 1
            err = (resp.error or "").lower()
            # Grinding through a spent daily budget wastes wall-clock and can
            # earn a longer ban; stop this endpoint and let the rest proceed.
            if "quota exhausted" in err or "rate limit" in err or "429" in err:
                stats["stopped"] = resp.error
                print(f"  [{provider}] {model}: stopping - {resp.error}", flush=True)
                return stats
            if stats["failed"] >= 10 and stats["ok"] == 0:
                stats["stopped"] = "10 consecutive failures, no successes"
                print(f"  [{provider}] {model}: stopping - {stats['stopped']}", flush=True)
                return stats

    return stats


async def census_provider(backend, writer, provider, models, probes, repeats):
    out = []
    for model in models:
        print(f"  [{provider}] {model} ...", flush=True)
        st = await census_endpoint(backend, writer, provider, model, probes, repeats)
        print(f"  [{provider}] {model} -> sent {st['sent']}, ok {st['ok']}, "
              f"failed {st['failed']}, skipped {st['skipped']}", flush=True)
        out.append(st)
        if st["stopped"] and "quota" in (st["stopped"] or "").lower():
            break  # the whole provider is spent, not just this model
    return out


async def main_async(args: argparse.Namespace) -> int:
    probes = probe_set(args.suite_name)
    roster = load_roster(args.mock, args.only)
    if not roster:
        print("Nothing to census.")
        return 1

    corpus_root = Path(args.corpus) if args.corpus else None
    writer = CorpusWriter(corpus_root)

    providers: dict[str, Any] = {}
    if not args.mock:
        from shim.backends import load_providers
        providers = {
            n: p for n, p in load_providers().items() if p.configured and p.enabled
        }
        roster = [(p, m) for p, m in roster if p in providers]
        if not roster:
            print("No configured providers for this roster. Run scripts/00_keys.py.")
            return 1

    todo, blocked = plan(roster, probes, args.repeats, writer, providers)
    if not sum(todo.values()):
        print("\nCorpus already complete for this roster. Nothing to do.")
        writer.write_manifest({"suite": SUITE, "repeats": args.repeats})
        return 0
    if blocked and not args.force:
        print(f"\n{blocked} provider(s) would exceed their measured daily cap. "
              f"Re-run with --only to narrow the roster, or --force to proceed anyway.")
        return 1
    if not args.yes:
        print("\nDry run. Re-run with --yes to actually record.")
        return 0

    print("\nRecording...\n")
    if args.mock:
        backend: Any = MockBackend(session_seed=args.seed)
        results = await census_provider(
            backend, writer, "mock", [m for _, m in roster], probes, args.repeats
        )
    else:
        from shim.backends import Client
        quota = QuotaManager(budgets_from_providers(providers))
        async with Client() as client:
            backend = LiveBackend(client, providers, quota)
            by_provider: dict[str, list[str]] = {}
            for p, m in roster:
                by_provider.setdefault(p, []).append(m)
            # Concurrent ACROSS providers, sequential within one: the rate limit
            # is per provider, so parallelism between them is free and
            # parallelism inside one only buys 429s.
            results = [
                st
                for group in await asyncio.gather(*[
                    census_provider(backend, writer, p, ms, probes, args.repeats)
                    for p, ms in by_provider.items()
                ])
                for st in group
            ]
        print("\n" + quota.report())

    manifest = writer.write_manifest({
        "suite": SUITE, "repeats": args.repeats,
        "cells": [p.cell for p in probes],
        "mock": args.mock,
    })

    sent = sum(s["sent"] for s in results)
    ok = sum(s["ok"] for s in results)
    print("\n" + "=" * 76)
    print(f"Recorded {ok}/{sent} responses across {len(results)} endpoints.")
    stopped = [s for s in results if s["stopped"]]
    if stopped:
        print(f"{len(stopped)} endpoint(s) stopped early - re-run to resume:")
        for s in stopped:
            print(f"  {s['endpoint']}: {s['stopped']}")
    print(f"  corpus:   {writer.root}")
    print(f"  manifest: {manifest.relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Record the probe census into corpus/.")
    ap.add_argument("--yes", action="store_true", help="actually make requests")
    ap.add_argument("--mock", action="store_true",
                    help="census the mock backend: no keys, no quota, no network")
    ap.add_argument("--only", nargs="*", default=None,
                    help="limit to these providers or model slugs")
    ap.add_argument("--repeats", type=int, default=30,
                    help="repeats per cell (Bruckner's operating point is 30)")
    ap.add_argument("--suite-name", default="core", choices=["core", "extended"])
    ap.add_argument("--corpus", default=None, help="corpus directory (default: corpus/)")
    ap.add_argument("--seed", type=int, default=7, help="mock session seed")
    ap.add_argument("--force", action="store_true",
                    help="proceed even if a provider's plan exceeds its daily cap")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
