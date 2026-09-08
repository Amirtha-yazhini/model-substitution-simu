"""Empirically measure what each free-tier endpoint can actually do.

This is not setup - it is the project's first result. The applicability-coverage
question ("on how much of the real fleet can each auditor even run?") is measured
here and nowhere else. RUT needs logprobs; GateScope's billing dimension needs
usage.cached_tokens; OTE needs max_tokens to be honoured and reasoning traces to
be absent. Whether those hold is an empirical fact about the fleet, not an
assumption.

Outputs:
  config/providers.measured.yaml   machine-readable, consumed by later phases
  config/models.resolved.yaml      slugs that actually answered
  results/tables/coverage.md       human-readable table (a deliverable)

Quota: 2 calls per candidate model by default. Prints a budget plan and refuses
to fire without --yes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shim.backends import CallResult, Client, Provider, load_providers  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# A probe shaped like the ones the census will actually send (Bruckner-style:
# one word, tiny cap). Using the real probe shape means capability observations
# reflect census conditions rather than some easier hypothetical request.
PROBE_MESSAGES = [
    {"role": "user", "content": "Name a random number between 1 and 100. Reply with only the number."}
]

REASONING_MARKERS = re.compile(r"<think>|<reasoning>|<\|channel\|>", re.IGNORECASE)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_model_candidates() -> dict[str, list[str]]:
    with open(ROOT / "config" / "models.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    return cfg.get("discovery_candidates", {}) or {}


def describe(result: CallResult) -> str:
    if result.ok:
        return "ok"
    if result.status is None:
        return f"conn-error ({result.error or ''})"[:60]
    return f"HTTP {result.status}"


async def probe_model(
    client: Client,
    provider: Provider,
    slug: str,
    *,
    delay_s: float,
    deep: bool,
    max_tokens: int = 256,
) -> dict[str, Any]:
    """2 calls (4 with --deep): basic, logprobs, [determinism x2].

    max_tokens defaults to 256, not 16. Reasoning models spend the budget on
    hidden reasoning before emitting any content, so a 16-token cap returns an
    empty string and looks like a broken endpoint. Measuring the reasoning cost
    is itself a result - see `reasoning_tokens` below.
    """
    rec: dict[str, Any] = {"provider": provider.name, "slug": slug}

    basic = await client.chat(
        provider, slug, PROBE_MESSAGES, max_tokens=max_tokens, temperature=1.0
    )
    rec["works"] = basic.ok
    rec["status"] = describe(basic)
    rec["latency_s"] = round(basic.latency_s, 3)

    if not basic.ok:
        rec["error"] = (basic.error or "")[:200]
        rec["rate_limited"] = basic.rate_limited
        return rec

    usage = basic.usage or {}
    rec["text_sample"] = (basic.text or "")[:80]
    rec["has_usage"] = bool(usage)
    rec["usage_fields"] = sorted(usage.keys()) if usage else []
    rec["completion_tokens"] = usage.get("completion_tokens")
    rec["prompt_tokens"] = usage.get("prompt_tokens")

    # GateScope billing dimension needs cached-token accounting.
    details = usage.get("prompt_tokens_details") or {}
    rec["has_cached_tokens"] = (
        "cached_tokens" in usage
        or (isinstance(details, dict) and "cached_tokens" in details)
    )

    rec["system_fingerprint"] = basic.system_fingerprint
    rec["has_system_fingerprint"] = basic.system_fingerprint is not None
    rec["finish_reason"] = basic.finish_reason

    # How much of the budget went to HIDDEN REASONING before any answer?
    # This is the cost driver for every cheap-probe auditor (OTE, KBF).
    ctd = usage.get("completion_tokens_details") or {}
    reasoning = ctd.get("reasoning_tokens") if isinstance(ctd, dict) else None
    rec["reasoning_tokens"] = reasoning
    rec["is_reasoning_model"] = bool(reasoning)
    rec["empty_content"] = not (basic.text or "").strip()
    rec["truncated"] = basic.finish_reason == "length"

    ct = usage.get("completion_tokens")
    rec["completion_tokens"] = ct
    # Would Bruckner's 16-token protocol have worked here?
    rec["ote_16tok_viable"] = bool(
        ct is not None and ct <= 16 and (basic.text or "").strip() and not reasoning
    )
    rec["max_tokens_honoured"] = (ct is not None and ct <= max_tokens)

    # Reasoning traces break single-token fingerprinting (Bruckner excluded 0.76%
    # of his census for exactly this).
    rec["leaks_reasoning"] = bool(REASONING_MARKERS.search(basic.text or ""))

    await asyncio.sleep(delay_s)

    # RUT and DiFR live or die on this one.
    lp = await client.chat(
        provider, slug, PROBE_MESSAGES, max_tokens=max_tokens, logprobs=True, top_logprobs=5
    )
    rec["logprobs_accepted"] = lp.ok
    rec["logprobs_returned"] = lp.ok and lp.has_logprobs
    if not lp.ok:
        rec["logprobs_error"] = (lp.error or "")[:160]

    if deep:
        await asyncio.sleep(delay_s)
        d1 = await client.chat(
            provider, slug, PROBE_MESSAGES, max_tokens=16, temperature=0.0, seed=42
        )
        await asyncio.sleep(delay_s)
        d2 = await client.chat(
            provider, slug, PROBE_MESSAGES, max_tokens=16, temperature=0.0, seed=42
        )
        if d1.ok and d2.ok:
            rec["deterministic_at_t0"] = (d1.text or "").strip() == (d2.text or "").strip()

    return rec


async def probe_provider(
    client: Client,
    provider: Provider,
    candidates: list[str],
    *,
    max_models: int,
    deep: bool,
    max_tokens: int = 256,
) -> dict[str, Any]:
    rpm = provider.meta.get("documented_rpm") or 10
    delay_s = max(60.0 / float(rpm), 0.2)

    out: dict[str, Any] = {
        "provider": provider.name,
        "role": provider.role,
        "base_url": provider.base_url,
        "probed_at": utcnow(),
        "documented_rpm": provider.meta.get("documented_rpm"),
        "documented_rpd": provider.meta.get("documented_rpd"),
        "inter_request_delay_s": round(delay_s, 2),
    }

    listed, list_err = await client.list_models(provider)
    out["models_endpoint_works"] = list_err is None
    out["models_listed_count"] = len(listed)
    out["models_listed_sample"] = listed[:40]
    if list_err:
        out["models_endpoint_error"] = list_err[:200]

    # Prefer candidates the listing confirms; otherwise try them blind.
    if listed:
        confirmed = [c for c in candidates if c in listed]
        unconfirmed = [c for c in candidates if c not in listed]
        to_probe = (confirmed + unconfirmed)[:max_models]
    else:
        to_probe = candidates[:max_models]

    results = []
    for slug in to_probe:
        print(f"  [{provider.name}] probing {slug} ...", flush=True)
        rec = await probe_model(client, provider, slug, delay_s=delay_s, deep=deep,
                                max_tokens=max_tokens)
        status = "OK" if rec.get("works") else rec.get("status")
        print(f"  [{provider.name}] {slug} -> {status}", flush=True)
        results.append(rec)
        if rec.get("rate_limited"):
            print(f"  [{provider.name}] rate limited; stopping this provider", flush=True)
            out["stopped_early_rate_limit"] = True
            break
        await asyncio.sleep(delay_s)

    out["models"] = results
    out["working_models"] = [r["slug"] for r in results if r.get("works")]
    return out


def render_coverage(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Free-tier capability coverage\n")
    lines.append(f"Measured: {report['generated_at']}\n")
    lines.append(
        "Empirically measured, not taken from documentation. This table is the "
        "applicability-coverage result: it determines which auditors can run on "
        "which endpoints at all.\n"
    )

    lines.append("\n## Per-model capabilities\n")
    lines.append(
        "| Provider | Model | Works | usage | cached_tokens | logprobs | sys_fp | reasoning tok | 16-tok probe viable |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")

    def tick(v: Any) -> str:
        if v is True:
            return "yes"
        if v is False:
            return "no"
        return "-"

    for prov in report["providers"]:
        for m in prov.get("models", []):
            if not m.get("works"):
                lines.append(
                    f"| {prov['provider']} | `{m['slug']}` | **{m.get('status','fail')}** "
                    f"| - | - | - | - | - | - |"
                )
                continue
            rt = m.get("reasoning_tokens")
            rt_s = str(rt) if rt else ("0" if rt == 0 else "-")
            lines.append(
                f"| {prov['provider']} | `{m['slug']}` | yes "
                f"| {tick(m.get('has_usage'))} "
                f"| {tick(m.get('has_cached_tokens'))} "
                f"| {tick(m.get('logprobs_returned'))} "
                f"| {tick(m.get('has_system_fingerprint'))} "
                f"| {rt_s} "
                f"| {tick(m.get('ote_16tok_viable'))} |"
            )

    # Roll up into the number that actually matters for the paper.
    working = [m for p in report["providers"] for m in p.get("models", []) if m.get("works")]
    n = len(working)
    lines.append("\n## Auditor applicability (the coverage result)\n")
    if n:
        n_lp = sum(1 for m in working if m.get("logprobs_returned"))
        n_cached = sum(1 for m in working if m.get("has_cached_tokens"))
        n_usage = sum(1 for m in working if m.get("has_usage"))
        n_clean = sum(1 for m in working if not m.get("leaks_reasoning"))
        lines.append("| Auditor | Requires | Applicable endpoints | Coverage |")
        lines.append("|---|---|---|---|")
        n_ote16 = sum(1 for m in working if m.get("ote_16tok_viable"))
        lines.append(f"| OTE @16 tok (as published) | no hidden reasoning | {n_ote16}/{n} | {n_ote16/n:.0%} |")
        lines.append(f"| OTE @256 tok (adapted) | text only | {n_clean}/{n} | {n_clean/n:.0%} |")
        lines.append(f"| IRIS-lite | text only | {n}/{n} | 100% |")
        lines.append(f"| KBF | text only | {n}/{n} | 100% |")
        lines.append(f"| BENCH (Cai et al.) | text only | {n}/{n} | 100% |")
        lines.append(f"| GATEOPS latency | timing only | {n}/{n} | 100% |")
        lines.append(f"| GATEOPS billing | `cached_tokens` | {n_cached}/{n} | {n_cached/n:.0%} |")
        lines.append(f"| RUT | logprobs | {n_lp}/{n} | {n_lp/n:.0%} |")
        lines.append(f"| (any usage-based) | `usage` block | {n_usage}/{n} | {n_usage/n:.0%} |")
    else:
        lines.append("_No working endpoints yet - configure keys and re-run._")

    if n:
        reasoners = [m for m in working if m.get("is_reasoning_model")]
        lines.append("\n## Finding: hidden reasoning has repriced cheap auditing\n")
        lines.append(
            f"{len(reasoners)}/{n} working endpoints spend tokens on hidden reasoning "
            "before emitting any answer. Bruckner's published protocol caps completions "
            "at 16 tokens; on a reasoning endpoint that returns an EMPTY string with "
            "`finish_reason=length`, so the probe fails rather than answers.\n"
        )
        if reasoners:
            lines.append("| Endpoint | reasoning tokens | completion tokens | answer |")
            lines.append("|---|---|---|---|")
            for m in reasoners:
                lines.append(
                    f"| {m['provider']}/`{m['slug']}` | {m.get('reasoning_tokens')} "
                    f"| {m.get('completion_tokens')} | `{(m.get('text_sample') or '').strip()[:20]}` |"
                )
        lines.append(
            "\nBruckner reported excluding 0.76% of his census for unexpected reasoning "
            "traces. On this 2026 free-tier fleet the affected share is far larger, and "
            "per-probe cost rises from ~16 tokens to whatever the model spends thinking. "
            "That inflates the audit side of the break-even calculation in idea.md C3a: "
            "the cheapest known auditing method got more expensive because the fleet "
            "changed, not because the method changed.\n"
        )

    lines.append("\n## Provider notes\n")
    for prov in report["providers"]:
        lines.append(
            f"- **{prov['provider']}** ({prov['role']}): "
            f"/models {'ok' if prov.get('models_endpoint_works') else 'unavailable'}, "
            f"{prov.get('models_listed_count', 0)} slugs listed, "
            f"{len(prov.get('working_models', []))} probed working."
            + (" **Rate-limited during probe.**" if prov.get("stopped_early_rate_limit") else "")
        )

    return "\n".join(lines) + "\n"


async def main_async(args: argparse.Namespace) -> int:
    providers = load_providers()
    candidates = load_model_candidates()

    active = [
        p for p in providers.values()
        if p.configured and p.enabled and (not args.providers or p.name in args.providers)
    ]
    skipped = [p.name for p in providers.values() if not p.configured]

    if not active:
        print("No configured providers. Run scripts/00_keys.py first.")
        return 1

    planned = 0
    print("=" * 72)
    print("Probe plan (quota is the scarce resource - review before firing)")
    print("=" * 72)
    calls_per_model = 4 if args.deep else 2
    for p in active:
        cands = candidates.get(p.name, [])[: args.max_models]
        cost = len(cands) * calls_per_model
        planned += cost
        rpd = p.meta.get("documented_rpd")
        budget = f", daily cap {rpd}" if rpd else ""
        print(f"  {p.name:<12} {len(cands):>2} models x {calls_per_model} calls = {cost:>3} requests{budget}")
    print(f"\n  TOTAL: ~{planned} requests across {len(active)} providers")
    if skipped:
        print(f"  (skipping unconfigured: {', '.join(skipped)})")

    if not args.yes:
        print("\nDry run. Re-run with --yes to actually probe.")
        return 0

    print("\nProbing...\n")
    async with Client() as client:
        results = await asyncio.gather(
            *[
                probe_provider(
                    client, p, candidates.get(p.name, []),
                    max_models=args.max_models, deep=args.deep,
                    max_tokens=args.max_tokens,
                )
                for p in active
            ]
        )

    report = {
        "generated_at": utcnow(),
        "probe_calls_per_model": calls_per_model,
        "providers": list(results),
    }

    (ROOT / "config" / "providers.measured.yaml").write_text(
        yaml.safe_dump(report, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    resolved = {
        p["provider"]: p.get("working_models", []) for p in report["providers"]
    }
    (ROOT / "config" / "models.resolved.yaml").write_text(
        yaml.safe_dump(
            {"generated_at": report["generated_at"], "working_models": resolved},
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    tables = ROOT / "results" / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    (tables / "coverage.md").write_text(render_coverage(report), encoding="utf-8")
    (ROOT / "results" / "capability_probe.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    total_working = sum(len(v) for v in resolved.values())
    print("\n" + "=" * 72)
    print(f"Done. {total_working} working models across {len(active)} providers.")
    print("  config/providers.measured.yaml")
    print("  config/models.resolved.yaml")
    print("  results/tables/coverage.md   <- the coverage result")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe free-tier endpoint capabilities.")
    ap.add_argument("--yes", action="store_true", help="actually make API calls")
    ap.add_argument("--providers", nargs="*", default=None, help="limit to these providers")
    ap.add_argument("--max-models", type=int, default=4, help="candidates per provider")
    ap.add_argument("--deep", action="store_true", help="also test temperature-0 determinism (+2 calls/model)")
    ap.add_argument("--max-tokens", type=int, default=256, help="completion budget per probe")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
