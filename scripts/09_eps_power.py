"""Dense eps sweep for the economics figures, against the SEALED thresholds.

The grid (07_grid.py) runs two seeds per dilution rate, which is enough for a
majority-vote table and nowhere near enough to estimate detection POWER: two
sessions give a power of 0, 0.5 or 1. The break-even analysis (F1, F2) needs a
per-session detection probability, so this script scores 20 fresh sessions per
rate for A3, and 20 for A11 (benign routing) as the matched false-positive arm.

Nothing is fitted. Thresholds come from config/protocol.yaml, verified against
its seal by the same loader the grid uses. Seeds 700-719 are disjoint from
calibration (100-199), the holdout (9000-9049), the grid (500-502) and the
threshold-audit blocks (400-499, 9000-9099).

Outputs:
  results/eps_power.jsonl      one scored session per line
  results/eps_power_meta.json  token mix and price ratio for the savings curve
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.runner import build_auditors, run_session  # noqa: E402
from shim.gateway import MOCK_LADDER  # noqa: E402
from shim.ledger import load_prices  # noqa: E402
from shim.policy import load_arm_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "eps_power.jsonl"
META = ROOT / "results" / "eps_power_meta.json"
LEDGER = ROOT / "results" / "ledger_eps.jsonl"

EPS = [0.02, 0.05, 0.10, 0.25, 0.50]
SEEDS = range(700, 720)


def _load_grid_module():
    # 07_grid.py is not importable by name (leading digit); load it by path so
    # the seal check, threshold application and scoring are the grid's own code.
    spec = importlib.util.spec_from_file_location("grid07", ROOT / "scripts" / "07_grid.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def main_async(args: argparse.Namespace) -> int:
    g = _load_grid_module()
    g.LEDGER = LEDGER               # score_arm reads the module global at call time
    LEDGER.unlink(missing_ok=True)

    protocol = g.load_protocol()
    cond = protocol.get("conditions", {})
    auditors = build_auditors(
        iris_trees=cond.get("iris_trees", 100),
        iris_splits=cond.get("iris_splits", 3),
        ote_perm=cond.get("ote_permutations", 200),
    )
    g.apply_thresholds(auditors, protocol)
    prices = load_prices()

    print("=" * 84)
    print("Dense eps sweep - detection power per session, sealed thresholds")
    print("=" * 84)
    print(f"  protocol sha256 {protocol['sha256'][:32]}...  VERIFIED\n")

    reference = await run_session("A0", cond.get("reference_seed", 1), LEDGER)

    # Token mix of one honest session, for the adversary's per-request saving.
    tin = sum(float((o.usage or {}).get("prompt_tokens") or 0)
              for obs in reference.values() for o in obs)
    tout = sum(float((o.usage or {}).get("completion_tokens") or 0)
               for obs in reference.values() for o in obs)
    gen = prices.get(f"mock:{MOCK_LADDER.advertised}", {})
    sub = prices.get(f"mock:{MOCK_LADDER.substitute.model}", {})  # an Endpoint, not a slug

    def cost(p):
        return (tin * float(p.get("input_per_mtok", 0)) +
                tout * float(p.get("output_per_mtok", 0))) / 1e6

    meta = {
        "protocol_sha256": protocol["sha256"],
        "seeds": [min(SEEDS), min(SEEDS) + args.n - 1],
        "prompt_tokens_per_session": tin,
        "completion_tokens_per_session": tout,
        "genuine_session_cost_usd": cost(gen),
        "substitute_session_cost_usd": cost(sub),
        "price_ratio_substitute_over_genuine": cost(sub) / cost(gen) if cost(gen) else None,
    }

    base = load_arm_config()
    seeds = list(SEEDS)[: args.n]
    rows = []
    t0 = time.perf_counter()
    plan = [("A3", eps) for eps in EPS] + [("A11", None)]
    for arm, eps in plan:
        cfg = {**base, "A3": {**base["A3"], "eps": eps}} if eps is not None else None
        batch = []
        for seed in seeds:
            r = await g.score_arm(auditors, reference, arm, seed, protocol, prices, cfg)
            r["split"] = "eps_power"
            r["eps"] = eps
            batch.append(r)
        rows += batch
        power = {
            n: sum(1 for r in batch if r["auditors"][n]["decision"] == "inconsistent") / len(batch)
            for n in g.AUDITOR_ORDER if n != "RUT"
        }
        label = f"A3 eps={eps}" if eps is not None else "A11 (genuine)"
        print(f"  {label:<14} " + "  ".join(f"{n}:{p:.0%}" for n, p in power.items())
              + f"   [{time.perf_counter() - t0:.0f}s]", flush=True)

    OUT.write_text("\n".join(json.dumps(r, default=str) for r in rows) + "\n", encoding="utf-8")
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT)} ({len(rows)} sessions) and {META.relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Dense eps sweep for detection power.")
    ap.add_argument("--n", type=int, default=20, help="sessions per rate (max 20)")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
