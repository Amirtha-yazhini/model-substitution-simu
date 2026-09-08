"""Run OTE-lite against all 12 adversary arms on the mock backend. No keys, $0.

This answers the question Phase 3 exists to answer: does a reimplemented auditor
actually separate honest from substituted traffic, and where does it fail?

Read the A4/A5/A10/A11 rows carefully - those are the arms designed to break it.
"""

from __future__ import annotations

import asyncio
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.auditors.ote import OTEAuditor  # noqa: E402
from arena.collect import collect  # noqa: E402
from arena.probes.ote_probes import probe_set  # noqa: E402
from shim.gateway import MOCK_LADDER, Gateway  # noqa: E402
from shim.ledger import Ledger, load_prices  # noqa: E402
from shim.mock import MockBackend  # noqa: E402
from shim.policy import load_arm_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "results" / "ledger_test.jsonl"
REPEATS = 30


def gw(arm: str, arm_cfg=None, *, seed: int = 0) -> Gateway:
    """A gateway on a fresh mock session. `seed` makes sampling independent
    between sessions while staying reproducible across runs."""
    return Gateway(
        MOCK_LADDER, arm, MockBackend(session_seed=seed),
        ledger=Ledger(path=LEDGER, prices=load_prices()),
        arm_cfg=arm_cfg or load_arm_config(),
    )


async def main() -> int:
    LEDGER.unlink(missing_ok=True)
    probes = probe_set("core")
    auditor = OTEAuditor()
    arm_cfg = load_arm_config()

    print("=" * 78)
    print(f"OTE-lite vs 12 arms  |  {len(probes)} cells x {REPEATS} repeats "
          f"= {len(probes) * REPEATS} probes/arm")
    print("=" * 78)

    # Reference fingerprint: one honest session, enrolled as ground truth.
    print("\nBuilding reference fingerprint from A0 (honest, session 1)...")
    reference = await collect(gw("A0", seed=1), probes, repeats=REPEATS)
    ref_fp = auditor.fingerprint(reference)
    print(f"  {len(ref_fp)}/{len(probes)} cells usable, modes: "
          + ", ".join(f"{c}={max(d, key=d.get)}" for c, d in sorted(ref_fp.items())))

    # Null calibration: INDEPENDENT honest sessions scored against that same
    # reference, at the same cell count and the same repeat depth every arm gets
    # below. Matching those conditions matters - an earlier version compared the
    # null at 8 cells/30-vs-30 against arms at 4 cells/30-vs-60 and the honest
    # control scored ABOVE the null ceiling, which is a pure artefact of the
    # mismatch, not a real false positive.
    print("\nNull calibration - independent honest sessions vs reference:")
    null_scores = []
    for s in range(2, 22):
        obs = await collect(gw("A0", seed=s), probes, repeats=REPEATS)
        r = auditor.audit(obs, reference)
        if r.applicable:
            null_scores.append(r.score)
    null_p95 = sorted(null_scores)[int(0.95 * (len(null_scores) - 1))]
    print(f"  mean JSD {statistics.mean(null_scores):.4f}  "
          f"p95 {null_p95:.4f}  max {max(null_scores):.4f}  n={len(null_scores)}")

    print(f"\n{'arm':<5} {'name':<24} {'JSD':>7} {'cells':>6} {'truth':>12}  note")
    print("-" * 78)

    rows = []
    for i in range(12):
        arm = f"A{i}"
        g = gw(arm, seed=100 + i)
        obs = await collect(g, probes, repeats=REPEATS)
        res = auditor.audit(obs, reference)

        import json
        truth_sub = 0
        with open(LEDGER, encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                if d["arm"] == arm and not d["is_genuine"]:
                    truth_sub += 1

        name = arm_cfg.get(arm, {}).get("name", "?")
        if not res.applicable:
            print(f"{arm:<5} {name:<24} {'n/a':>7} {'-':>6} {truth_sub:>12}  "
                  f"UNINFORMATIVE: {res.detail.get('reason','')[:28]}")
            rows.append((arm, name, None, truth_sub))
            continue

        n_cells = res.detail["n_cells"]
        note = ""
        if arm == "A0":
            note = "control"
        elif arm in ("A4", "A11"):
            note = "GENUINE weights - flagging = false positive"
        elif arm in ("A5", "A10"):
            note = "evasion: probes got the honest model"
        print(f"{arm:<5} {name:<24} {res.score:>7.4f} {n_cells:>6} {truth_sub:>12}  {note}")
        rows.append((arm, name, res.score, truth_sub))

    # ---- interpretation ----
    print("\n" + "=" * 78)
    d = {a: s for a, s, in [(r[0], r[2]) for r in rows]}
    null_max = null_p95
    print(f"Null ceiling (independent honest sessions, p95): {null_max:.4f}")

    def verdict(arm: str, expect_detect: bool) -> str:
        s = d.get(arm)
        if s is None:
            return "uninformative"
        detected = s > null_max
        if expect_detect:
            return "DETECTED" if detected else "MISSED"
        return "false positive" if detected else "correctly clean"

    print(f"\n  A1 full substitution   -> {verdict('A1', True)}")
    print(f"  A3 dilution (eps=0.10) -> {verdict('A3', True)}")
    print(f"  A5 probe-aware evasion -> {verdict('A5', True)}   <- the novel attack")
    print(f"  A10 canary-aware       -> {verdict('A10', True)}   <- the novel attack")
    print(f"  A4 sampler retune      -> {verdict('A4', False)}   <- specificity test")
    print(f"  A11 benign routing     -> {verdict('A11', False)}   <- THE CONFOUND")

    print("\nInterpretation:")
    if d.get("A5") is not None and d.get("A5") <= null_max:
        print("  * A5 defeats OTE completely. The gateway serves the honest model to")
        print("    anything probe-shaped, and OTE's probes are the most probe-shaped")
        print("    traffic imaginable. No source paper evaluates this attack.")
    if d.get("A4") is not None and d.get("A1") is not None and d.get("A4") > d.get("A1"):
        print("  * SPECIFICITY FAILURE: A4 (sampler retune, GENUINE weights) scores")
        print(f"    {d['A4']:.3f} vs A1 (real substitution) {d['A1']:.3f}. OTE flags a")
        print("    temperature change HARDER than an actual model swap - it detects")
        print("    'the distribution moved', not 'the model changed'. IRIS declares")
        print("    this case out of scope, so nobody has measured it until now.")
    if d.get("A3") is not None and d.get("A3") <= null_max:
        print("  * A3 (eps=0.10) is missed at this budget, as IRIS's Theta(1/eps)")
        print("    query complexity predicts. Detecting it needs more probes, which")
        print("    is exactly the cost the break-even analysis prices.")
    if d.get("A6") is not None and d.get("A6") > d.get("A1", 0):
        print("  * A6 (cache replay) scores highest of all - but for the WRONG reason:")
        print("    caching collapses the answer distribution to a point mass. OTE is")
        print("    detecting determinism, not substitution.")
    if d.get("A11") is not None and d.get("A11") <= null_max:
        print("  * A11 is NOT flagged here, because this mock's alternate provider is")
        print("    near-identical to genuine. How severe the confound really is depends")
        print("    on how much real providers of the same model differ - an empirical")
        print("    question the live census answers, not the simulator.")

    # Write the deliverable table.
    out = ROOT / "results" / "tables" / "ote_arms.md"
    lines = ["# OTE-lite vs the 12 adversary arms (mock backend)\n",
             f"Probes: {len(probes)} cells x {REPEATS} repeats = {len(probes)*REPEATS} per arm. "
             f"Null: 20 independent honest sessions vs the same reference.\n",
             f"Null ceiling (p95): **{null_max:.4f}**  |  null mean: {statistics.mean(null_scores):.4f}\n",
             "| Arm | Name | Mean JSD | vs null | True substitution rate |",
             "|---|---|---|---|---|"]
    for arm, name, score, truth in rows:
        if score is None:
            lines.append(f"| {arm} | {name} | uninformative | - | {truth}/{len(probes)*REPEATS} |")
        else:
            flag = "**FLAGGED**" if score > null_max else "clean"
            lines.append(f"| {arm} | {name} | {score:.4f} | {flag} | {truth}/{len(probes)*REPEATS} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
