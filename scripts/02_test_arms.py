"""Exercise all 12 adversary arms against the mock backend. No API keys, no cost.

This is the Phase 1 acceptance test. It checks the properties the rest of the
project depends on:

  1. every arm routes and returns a valid OpenAI-shaped body
  2. the client NEVER sees the true backend - the advertised slug is always echoed
  3. A3's dilution rate is actually eps, and is deterministic across replays
  4. A5 and A10 evade probes but substitute ordinary traffic
  5. A11 keeps is_genuine=True while still splitting traffic (the confound)
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shim.gateway import MOCK_LADDER, Gateway  # noqa: E402
from shim.ledger import Ledger, load_prices  # noqa: E402
from shim.mock import MockBackend  # noqa: E402
from shim.policy import load_arm_config  # noqa: E402
from shim.types import AuditRequest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT / "results" / "ledger_test.jsonl"

PROBE = "Name a random number between 1 and 100. Reply with only the number."
ORDINARY = (
    "I am refactoring a payment reconciliation service that ingests settlement "
    "files from three providers. Walk me through how you would restructure the "
    "retry logic so that partial failures do not double-charge a customer, and "
    "explain the trade-offs between idempotency keys and a transactional outbox."
)
CANARY = "Natalia sold clips to 48 of her friends in April, and then she sold half as many in May."


def make_req(prompt: str, *, max_tokens: int = 16, nonce: int | None = None) -> AuditRequest:
    messages = [{"role": "user", "content": prompt}]
    raw = {"model": MOCK_LADDER.advertised, "messages": messages, "max_tokens": max_tokens}
    if nonce is not None:
        raw["_nonce"] = nonce  # varies the body hash for dilution sampling
    return AuditRequest(
        model=MOCK_LADDER.advertised, messages=messages, max_tokens=max_tokens,
        temperature=None, top_p=None, logprobs=False, seed=None, raw=raw,
    )


async def run_arm(arm: str, requests: list[AuditRequest]) -> list[dict]:
    gw = Gateway(
        MOCK_LADDER, arm, MockBackend(),
        ledger=Ledger(path=LEDGER_PATH, prices=load_prices()),
        arm_cfg=load_arm_config(),
    )
    rows = []
    for req in requests:
        body, row = await gw.handle(req)
        row["_client_model"] = (body or {}).get("model")
        row["_client_text"] = ((body or {}).get("choices") or [{}])[0].get("message", {}).get("content")
        rows.append(row)
    return rows


async def main() -> int:
    LEDGER_PATH.unlink(missing_ok=True)
    failures: list[str] = []

    print("=" * 74)
    print("Phase 1 acceptance: 12 adversary arms vs mock backend (no keys, $0)")
    print("=" * 74)

    probes = [make_req(PROBE, nonce=i) for i in range(200)]

    print(f"\n{'arm':<5} {'name':<24} {'substituted':>12} {'genuine':>8}  backends")
    print("-" * 74)

    summary: dict[str, dict] = {}
    for arm in [f"A{i}" for i in range(12)]:
        rows = await run_arm(arm, probes)
        subbed = sum(1 for r in rows if not r["is_genuine"])
        backends = Counter(r["true_model"] for r in rows)
        name = rows[0]["arm"],
        cfg = load_arm_config().get(arm, {})
        summary[arm] = {"rows": rows, "subbed": subbed, "backends": backends}

        # invariant 2: the advertised slug must always be echoed
        leaked = [r for r in rows if r["_client_model"] != MOCK_LADDER.advertised]
        if leaked:
            failures.append(f"{arm}: leaked true model to client ({leaked[0]['_client_model']})")

        bstr = ", ".join(f"{k}={v}" for k, v in backends.most_common())
        print(f"{arm:<5} {cfg.get('name','?'):<24} {subbed:>7}/{len(rows):<4} "
              f"{len(rows)-subbed:>8}  {bstr}")

    # ---- invariant 3: dilution rate is correct and deterministic ----
    print("\n" + "-" * 74)
    print("A3 dilution sweep: observed rate vs expected")
    print("  Gate is |z| < 4, not 95%. Rationale: sampler uniformity is verified")
    print("  separately and far more powerfully (KS at n=50,000, p=0.36); this")
    print("  check exists to catch GROSS errors (wrong eps, inverted comparison),")
    print("  so it must not flake on 2-sigma noise. All eps also share one set of")
    print("  request hashes, making deviations correlated across rows by design.")
    arm_cfg = load_arm_config()
    sweep_reqs = [make_req(PROBE, nonce=i) for i in range(2000)]
    n = len(sweep_reqs)
    for eps in arm_cfg["A3"]["sweep"]:
        cfg = {**arm_cfg, "A3": {**arm_cfg["A3"], "eps": eps}}
        gw = Gateway(MOCK_LADDER, "A3", MockBackend(),
                     ledger=Ledger(path=LEDGER_PATH, prices=load_prices()), arm_cfg=cfg)
        n_sub = 0
        for req in sweep_reqs:
            _, row = await gw.handle(req)
            n_sub += 0 if row["is_genuine"] else 1
        observed = n_sub / n
        se = (eps * (1 - eps) / n) ** 0.5
        z = (observed - eps) / se
        ok = abs(z) < 4.0
        print(f"  eps={eps:<5} expected {eps:>6.2%}  observed {observed:>6.2%}  "
              f"z={z:+.2f}  {'ok' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"A3 eps={eps}: observed {observed:.4f}, z={z:+.2f}")

    # determinism: identical inputs must reproduce identical routing
    r1 = await run_arm("A3", probes)
    r2 = await run_arm("A3", probes)
    if [r["is_genuine"] for r in r1] != [r["is_genuine"] for r in r2]:
        failures.append("A3: routing not deterministic across replays")
    else:
        print("  determinism: identical routing across two replays  ok")

    # ---- invariant 4: evasion arms behave differently by traffic type ----
    print("\n" + "-" * 74)
    print("Evasion arms: probe traffic vs ordinary traffic")
    mixed_probe = [make_req(PROBE, nonce=i) for i in range(50)]
    mixed_ord = [make_req(ORDINARY, max_tokens=512, nonce=i) for i in range(50)]
    mixed_canary = [make_req(CANARY, max_tokens=256, nonce=i) for i in range(50)]

    for arm, traffic_sets in [
        ("A5", [("probe", mixed_probe), ("ordinary", mixed_ord)]),
        ("A10", [("canary", mixed_canary), ("ordinary", mixed_ord)]),
    ]:
        for label, traffic in traffic_sets:
            rows = await run_arm(arm, traffic)
            sub_rate = sum(1 for r in rows if not r["is_genuine"]) / len(rows)
            print(f"  {arm} on {label:<9} substitution rate {sub_rate:>6.1%}")
            if label in ("probe", "canary") and sub_rate > 0.10:
                failures.append(f"{arm}: failed to evade on {label} traffic ({sub_rate:.1%})")
            if label == "ordinary" and sub_rate < 0.90:
                failures.append(f"{arm}: failed to substitute ordinary traffic ({sub_rate:.1%})")

    # ---- invariant 5: A11 splits traffic but stays genuine ----
    print("\n" + "-" * 74)
    a11 = summary["A11"]
    a3 = summary["A3"]
    print("The confound (idea.md section 5):")
    print(f"  A3  backends={dict(a3['backends'])}  is_genuine=False on {a3['subbed']}/200")
    print(f"  A11 backends={dict(a11['backends'])}  is_genuine=False on {a11['subbed']}/200")
    if a11["subbed"] != 0:
        failures.append("A11 must never be labelled substitution - it serves correct weights")
    if len(a11["backends"]) < 2:
        failures.append("A11 must actually split traffic across providers")
    else:
        print("  -> A11 splits traffic like A3 yet is not fraud. Auditors must separate these.")

    print("\n" + "=" * 74)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"All invariants hold. Ledger: {LEDGER_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
