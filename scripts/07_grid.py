"""Phase 5 - the evaluation grid, scored against the SEALED thresholds.

12 arms x 7 auditors x N seeds, plus the eps sweep on A3 (fraud) and A11 (benign
routing), plus the untouched holdout of honest sessions that measures the
realised false-positive rate.

Nothing here fits anything. Thresholds come from config/protocol.yaml, whose
SHA-256 is verified before a single session runs; if the file has been edited
since sealing, this script refuses rather than quietly reporting numbers from a
protocol that no longer matches its hash. That check is the whole value of Phase
4 - a seal nobody verifies is decoration.

Outputs:
  results/grid.jsonl                every cell, with e-values and per-channel detail
  results/tables/grid.md            auditors x arms decision matrix
  results/tables/eps_sweep.md       A3 vs A11 across dilution rates - the confound
  results/tables/coverage_arena.md  applicability per auditor per arm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.runner import audit_session, build_auditors, queries_per_session, run_session  # noqa: E402
from shim.ledger import load_prices  # noqa: E402
from shim.policy import load_arm_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "results" / "ledger_grid.jsonl"
PROTOCOL = ROOT / "config" / "protocol.yaml"
GRID = ROOT / "results" / "grid.jsonl"
TABLES = ROOT / "results" / "tables"

ARMS = [f"A{i}" for i in range(12)]
SEEDS_ARM = [500, 501, 502]                  # three independent realisations per arm
EPS_SWEEP = [0.02, 0.05, 0.10, 0.25, 0.50]
AUDITOR_ORDER = ["OTE", "IRIS-lite", "GATEOPS", "KBF", "BENCH", "RUT", "FUSE"]

# Ground truth per arm: is flagging it correct? A2 is the debatable one and is
# labelled substitution per config/arms.yaml; A4 and A11 serve the advertised
# weights, so flagging them is a FALSE POSITIVE however different they look.
IS_SUBSTITUTION = {
    "A0": False, "A1": True, "A2": True, "A3": True, "A4": False, "A5": True,
    "A6": True, "A7": True, "A8": True, "A9": True, "A10": True, "A11": False,
}


def load_protocol() -> dict[str, Any]:
    if not PROTOCOL.exists():
        raise SystemExit("config/protocol.yaml missing - run scripts/06_calibrate.py --write")
    doc = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8")) or {}

    # Verify the seal. A protocol whose hash no longer matches its contents has
    # been edited since it was frozen, which is exactly the failure the seal
    # exists to make visible.
    sys.path.insert(0, str(ROOT / "scripts"))
    import hashlib
    body = {k: v for k, v in doc.items() if k != "sha256"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    got = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    if got != doc.get("sha256"):
        raise SystemExit(
            f"PROTOCOL SEAL BROKEN\n  recorded: {doc.get('sha256')}\n  actual:   {got}\n"
            f"config/protocol.yaml was edited after sealing. Re-seal with a new "
            f"protocol_version and tag, and report the change."
        )
    return doc


def apply_thresholds(auditors: dict[str, Any], protocol: dict[str, Any]) -> None:
    for name, auditor in auditors.items():
        spec = (protocol.get("thresholds") or {}).get(name) or {}
        auditor.threshold = spec.get("threshold")


def decide(name: str, res, protocol) -> str:
    """FUSE decides on its e-value; everyone else on the sealed score threshold."""
    if not res.applicable:
        return "uninformative"
    if name == "FUSE":
        return res.decision
    thr = ((protocol.get("thresholds") or {}).get(name) or {}).get("threshold")
    if thr is None:
        return "uninformative"
    return "inconsistent" if res.score >= thr else "consistent"


async def score_arm(auditors, reference, arm, seed, protocol, prices, arm_cfg=None):
    session = await run_session(arm, seed, LEDGER, arm_cfg)
    results = audit_session(
        auditors, session, reference, prices=prices, alpha=protocol.get("alpha", 0.01)
    )
    row: dict[str, Any] = {
        "arm": arm, "seed": seed,
        "is_substitution": IS_SUBSTITUTION.get(arm),
        "queries": queries_per_session(),
        "auditors": {},
    }
    for name in AUDITOR_ORDER:
        res = results.get(name)
        if res is None:
            continue
        d = res.detail or {}
        row["auditors"][name] = {
            "decision": decide(name, res, protocol),
            "score": None if res.score != res.score else res.score,
            "e_value": res.e_value,
            "applicable": res.applicable,
            "p_value": d.get("p_value", d.get("fisher_p")),
            "cost_usd": res.cost_usd,
            "reason": d.get("reason") if not res.applicable else None,
        }
    return row


async def main_async(args: argparse.Namespace) -> int:
    protocol = load_protocol()
    print("=" * 84)
    print("Phase 5 - evaluation grid against the SEALED protocol")
    print("=" * 84)
    print(f"  protocol sha256 {protocol['sha256'][:32]}...  VERIFIED")
    print(f"  sealed at commit {protocol.get('git_commit','?')[:12]}, "
          f"alpha={protocol.get('alpha')}")
    print(f"  {queries_per_session()} queries/session\n")

    LEDGER.unlink(missing_ok=True)
    GRID.unlink(missing_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    prices = load_prices()
    t0 = time.perf_counter()

    cond = protocol.get("conditions", {})
    auditors = build_auditors(
        iris_trees=cond.get("iris_trees", 100),
        iris_splits=cond.get("iris_splits", 3),
        ote_perm=cond.get("ote_permutations", 200),
    )
    apply_thresholds(auditors, protocol)

    reference = await run_session("A0", cond.get("reference_seed", 1), LEDGER)
    rows: list[dict[str, Any]] = []

    # ---- holdout: honest sessions never seen during calibration ----
    lo, hi = cond.get("holdout_seeds", [9000, 9049])
    holdout_seeds = list(range(lo, hi + 1))[: args.holdout]
    print(f"Holdout - {len(holdout_seeds)} honest sessions vs frozen thresholds...")
    fp: dict[str, int] = {n: 0 for n in AUDITOR_ORDER}
    applicable_n: dict[str, int] = {n: 0 for n in AUDITOR_ORDER}
    for seed in holdout_seeds:
        r = await score_arm(auditors, reference, "A0", seed, protocol, prices)
        r["split"] = "holdout"
        rows.append(r)
        for name, a in r["auditors"].items():
            if a["applicable"]:
                applicable_n[name] += 1
                if a["decision"] == "inconsistent":
                    fp[name] += 1

    print(f"\n  {'auditor':<12} {'flagged':>8} {'applicable':>11}  realised FPR")
    print("  " + "-" * 52)
    fpr: dict[str, float | None] = {}
    for name in AUDITOR_ORDER:
        n = applicable_n[name]
        fpr[name] = (fp[name] / n) if n else None
        rate = f"{fpr[name]:.1%}" if n else "n/a (never applicable)"
        print(f"  {name:<12} {fp[name]:>8} {n:>11}  {rate}")

    # ---- the arms ----
    print(f"\nArms - {len(ARMS)} x {len(SEEDS_ARM)} seeds...")
    for arm in ARMS:
        for seed in SEEDS_ARM:
            r = await score_arm(auditors, reference, arm, seed, protocol, prices)
            r["split"] = "arms"
            rows.append(r)
        flags = [
            rr["auditors"] for rr in rows if rr["arm"] == arm and rr["split"] == "arms"
        ]
        summary = " ".join(
            f"{n.split('-')[0][:4]}:"
            + ("F" if sum(1 for f in flags if f[n]['decision'] == 'inconsistent') * 2 > len(flags)
               else "-" if any(f[n]['applicable'] for f in flags) else "u")
            for n in AUDITOR_ORDER
        )
        truth = "SUB" if IS_SUBSTITUTION[arm] else "genuine"
        print(f"  {arm:<4} {truth:<8} {summary}", flush=True)

    # ---- eps sweep: fraud vs sanctioned routing at matched traffic splits ----
    print("\nEps sweep - A3 (fraud) vs A11 (benign routing)...")
    base_cfg = load_arm_config()
    for eps in EPS_SWEEP:
        cfg = {**base_cfg, "A3": {**base_cfg["A3"], "eps": eps}}
        for seed in SEEDS_ARM[:2]:
            r = await score_arm(auditors, reference, "A3", seed, protocol, prices, cfg)
            r["split"] = "eps_sweep"
            r["eps"] = eps
            rows.append(r)
        print(f"  A3 eps={eps} done", flush=True)

    GRID.write_text(
        "\n".join(json.dumps(r, default=str) for r in rows) + "\n", encoding="utf-8"
    )
    write_tables(rows, protocol, fpr, applicable_n)
    print(f"\nWrote results/grid.jsonl ({len(rows)} cells) and 3 tables "
          f"in {time.perf_counter()-t0:.0f}s")
    return 0


def _majority(rows: list[dict], arm: str, name: str) -> tuple[str, float | None]:
    cells = [r["auditors"][name] for r in rows
             if r["arm"] == arm and r["split"] == "arms" and name in r["auditors"]]
    if not cells:
        return "-", None
    if not any(c["applicable"] for c in cells):
        return "uninformative", None
    flagged = sum(1 for c in cells if c["decision"] == "inconsistent")
    scores = [c["score"] for c in cells if c["score"] is not None]
    med = statistics.median(scores) if scores else None
    return ("inconsistent" if flagged * 2 > len(cells) else "consistent"), med


def write_tables(rows, protocol, fpr, applicable_n) -> None:
    arm_cfg = load_arm_config()
    mark = {"inconsistent": "**F**", "consistent": ".", "uninformative": "u", "-": "-"}

    # --- grid.md ---
    L = [
        "# Auditors x arms, against the sealed protocol\n",
        f"Protocol SHA-256 `{protocol['sha256']}` (tag `frozen-v1`), "
        f"alpha={protocol.get('alpha')}. No threshold was fitted after sealing.\n",
        "**F** = flagged (inconsistent), `.` = clean, `u` = uninformative "
        "(the auditor could not run - never scored as a pass).\n",
        "Majority over " + str(len(SEEDS_ARM)) + " seeds. `truth` is the ground-truth "
        "label from the ledger, which no auditor can see.\n",
        "| Arm | Name | truth | " + " | ".join(AUDITOR_ORDER) + " |",
        "|---|---|---|" + "---|" * len(AUDITOR_ORDER),
    ]
    for arm in ARMS:
        truth = "**substitution**" if IS_SUBSTITUTION[arm] else "genuine"
        cells = []
        for name in AUDITOR_ORDER:
            dec, med = _majority(rows, arm, name)
            cells.append(mark.get(dec, "-"))
        L.append(f"| {arm} | {arm_cfg.get(arm,{}).get('name','?')} | {truth} | "
                 + " | ".join(cells) + " |")

    L += ["", "## Realised false-positive rate on the untouched holdout", "",
          "| Auditor | flagged | applicable sessions | FPR | target |",
          "|---|---|---|---|---|"]
    for name in AUDITOR_ORDER:
        n = applicable_n[name]
        rate = f"{fpr[name]:.1%}" if n else "n/a"
        L.append(f"| {name} | {int((fpr[name] or 0)*n)} | {n} | {rate} | "
                 f"<= {protocol.get('conformal_fpr_bound', 0.01):.1%} |")

    L += ["", "## Median scores", "",
          "| Arm | " + " | ".join(AUDITOR_ORDER) + " |",
          "|---|" + "---|" * len(AUDITOR_ORDER)]
    for arm in ARMS:
        vals = []
        for name in AUDITOR_ORDER:
            _, med = _majority(rows, arm, name)
            vals.append("-" if med is None else (f"{med:+.3f}" if abs(med) < 1000 else f"{med:.3g}"))
        L.append(f"| {arm} | " + " | ".join(vals) + " |")
    (TABLES / "grid.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    # --- eps_sweep.md: the confound, quantified ---
    E = [
        "# The confound: dilution (A3) vs benign quality routing (A11)\n",
        "A3 serves a CHEAPER model on a fraction eps of requests. A11 splits traffic "
        "the same way across providers of the CORRECT model. Structurally identical; "
        "one is fraud and one is what every commercial router does openly.\n",
        "A11 is a FALSE-POSITIVE arm: any **F** in its row is an auditor calling "
        "sanctioned routing fraud.\n",
        "| eps | " + " | ".join(AUDITOR_ORDER) + " |",
        "|---|" + "---|" * len(AUDITOR_ORDER),
    ]
    for eps in EPS_SWEEP:
        cells = []
        for name in AUDITOR_ORDER:
            cs = [r["auditors"][name] for r in rows
                  if r.get("eps") == eps and name in r["auditors"]]
            if not cs or not any(c["applicable"] for c in cs):
                cells.append("u")
                continue
            flagged = sum(1 for c in cs if c["decision"] == "inconsistent")
            cells.append("**F**" if flagged * 2 > len(cs) else ".")
        E.append(f"| A3 @ {eps} | " + " | ".join(cells) + " |")
    a11 = []
    for name in AUDITOR_ORDER:
        dec, _ = _majority(rows, "A11", name)
        a11.append(mark.get(dec, "-"))
    E.append("| **A11 (genuine)** | " + " | ".join(a11) + " |")
    (TABLES / "eps_sweep.md").write_text("\n".join(E) + "\n", encoding="utf-8")

    # --- coverage_arena.md ---
    C = ["# Auditor applicability across arms\n",
         "`applicable=False` forces `uninformative`, never `consistent`. An auditor "
         "that cannot run is not an auditor that passed.\n",
         "| Auditor | applicable cells | total | coverage | reason when not |",
         "|---|---|---|---|---|"]
    for name in AUDITOR_ORDER:
        cells = [r["auditors"][name] for r in rows if name in r["auditors"]]
        ok = sum(1 for c in cells if c["applicable"])
        reasons = {c["reason"] for c in cells if c.get("reason")}
        why = next(iter(reasons), "-") if reasons else "-"
        C.append(f"| {name} | {ok} | {len(cells)} | {ok/max(len(cells),1):.0%} | "
                 f"{str(why)[:80]} |")
    (TABLES / "coverage_arena.md").write_text("\n".join(C) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the sealed-threshold evaluation grid.")
    ap.add_argument("--holdout", type=int, default=30,
                    help="holdout honest sessions to score (max 50)")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
