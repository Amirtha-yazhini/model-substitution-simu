"""Run OTE-lite against all 12 adversary arms on the mock backend. No keys, $0.

This answers the question Phase 3 exists to answer: does a reimplemented auditor
actually separate honest from substituted traffic, and where does it fail?

Calibration follows the protocol Phase 4 will seal, in miniature:

  * a CALIBRATION split of independent honest sessions sets the threshold,
  * a disjoint HOLDOUT split of honest sessions measures the realised FPR,
  * arms are scored only afterwards, against the frozen number.

The threshold is the calibration MAXIMUM, which is a conformal bound: under
exchangeability the probability that a fresh honest session exceeds the max of n
calibration sessions is at most 1/(n+1). At n=100 that is <1%, so the FPR target
is met by construction rather than by fitting a quantile to 20 points. That is
the whole reason the calibration split is this large - honest sessions cost
nothing on the mock, and buying the guarantee outright is cheaper than defending
an estimated quantile.

Read the A4/A5/A10/A11 rows carefully - those are the arms designed to break it.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
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
N_CALIB = 100        # honest sessions that set the threshold
N_HOLDOUT = 50       # disjoint honest sessions that measure the realised FPR
TARGET_FPR = 0.01

# Seed blocks are disjoint by construction, so calibration and holdout can never
# silently share a session - the failure mode that makes a holdout meaningless.
SEED_REFERENCE = 1
SEEDS_CALIB = range(100, 100 + N_CALIB)
SEEDS_HOLDOUT = range(9000, 9000 + N_HOLDOUT)
SEEDS_ARM = {f"A{i}": 500 + i for i in range(12)}


def gw(arm: str, arm_cfg=None, *, seed: int) -> Gateway:
    """A gateway on a fresh mock session. `seed` makes sampling independent
    between sessions while staying reproducible across runs."""
    return Gateway(
        MOCK_LADDER, arm, MockBackend(session_seed=seed),
        ledger=Ledger(path=LEDGER, prices=load_prices()),
        arm_cfg=arm_cfg or load_arm_config(),
    )


async def honest_scores(auditor, probes, reference, seeds) -> list[float]:
    out = []
    for s in seeds:
        obs = await collect(gw("A0", seed=s), probes, repeats=REPEATS)
        r = auditor.audit(obs, reference)
        if r.applicable:
            out.append(r.score)
    return out


async def main() -> int:
    LEDGER.unlink(missing_ok=True)
    probes = probe_set("core")
    auditor = OTEAuditor()
    arm_cfg = load_arm_config()
    t0 = time.perf_counter()

    print("=" * 78)
    print(f"OTE-lite vs 12 arms  |  {len(probes)} cells x {REPEATS} repeats "
          f"= {len(probes) * REPEATS} probes/arm")
    print(f"Statistic: permutation-debiased mean JSD ({auditor.n_perm} permutations/cell)")
    print("=" * 78)

    # Reference fingerprint: one honest session, enrolled as ground truth.
    print("\nBuilding reference fingerprint from A0 (honest, session 1)...")
    reference = await collect(gw("A0", seed=SEED_REFERENCE), probes, repeats=REPEATS)
    ref_fp = auditor.fingerprint(reference)
    print(f"  {len(ref_fp)}/{len(probes)} cells usable, modes: "
          + ", ".join(f"{c}={max(d, key=d.get)}" for c, d in sorted(ref_fp.items())))

    # ---- calibration split: sets the threshold, never scored against ----
    print(f"\nCalibration - {N_CALIB} independent honest sessions vs the reference...")
    calib = await honest_scores(auditor, probes, reference, SEEDS_CALIB)
    threshold = max(calib)
    conformal_fpr = 1.0 / (len(calib) + 1)
    print(f"  mean {statistics.mean(calib):+.4f}  sd {statistics.stdev(calib):.4f}  "
          f"min {min(calib):+.4f}  max {max(calib):+.4f}  n={len(calib)}")
    print(f"  threshold = calibration max = {threshold:+.4f}  "
          f"(conformal FPR bound <= 1/{len(calib)+1} = {conformal_fpr:.2%})")

    # ---- holdout split: measures what the threshold actually does ----
    print(f"\nHoldout - {N_HOLDOUT} further honest sessions, scored against the frozen threshold...")
    holdout = await honest_scores(auditor, probes, reference, SEEDS_HOLDOUT)
    false_pos = [s for s in holdout if s > threshold]
    emp_fpr = len(false_pos) / len(holdout)
    print(f"  mean {statistics.mean(holdout):+.4f}  max {max(holdout):+.4f}  n={len(holdout)}")
    print(f"  realised FPR {len(false_pos)}/{len(holdout)} = {emp_fpr:.1%}  "
          f"(target <= {TARGET_FPR:.0%})")

    # The debias correction is only credible if the honest null actually sits at
    # zero, so state it rather than leaving it to be inferred from the table.
    print(f"\n  Honest null centres at {statistics.mean(calib):+.4f} "
          f"(pre-correction it sat at +0.1755, above several real arms).")

    print(f"\n{'arm':<5} {'name':<24} {'JSD':>8} {'raw':>7} {'p':>9} "
          f"{'cells':>6} {'truth':>7}  note")
    print("-" * 92)

    rows = []
    for i in range(12):
        arm = f"A{i}"
        g = gw(arm, seed=SEEDS_ARM[arm])
        obs = await collect(g, probes, repeats=REPEATS)
        res = auditor.audit(obs, reference)

        # Ground truth, read from the ledger the auditor never sees. Only this
        # arm's own session is counted - the honest splits above wrote A0 rows.
        truth_sub = 0
        with open(LEDGER, encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                if d["arm"] == arm and not d["is_genuine"]:
                    truth_sub += 1
        if arm == "A0":
            truth_sub = 0  # every honest session is genuine by construction

        name = arm_cfg.get(arm, {}).get("name", "?")
        if not res.applicable:
            print(f"{arm:<5} {name:<24} {'n/a':>8} {'-':>7} {'-':>9} {'-':>6} "
                  f"{truth_sub:>7}  UNINFORMATIVE: {res.detail.get('reason','')[:24]}")
            rows.append((arm, name, None, None, None, truth_sub))
            continue

        d = res.detail
        note = ""
        if arm == "A0":
            note = "control"
        elif arm in ("A4", "A11"):
            note = "GENUINE weights - flagging = false positive"
        elif arm in ("A5", "A10"):
            note = "evasion: probes got the honest model"
        elif arm == "A2":
            note = "labelled fraud, serves alternate-70b (see footnote)"
        print(f"{arm:<5} {name:<24} {res.score:>+8.4f} {d['raw_mean_jsd']:>7.4f} "
              f"{d['fisher_p']:>9.2e} {d['n_cells']:>6} {truth_sub:>7}  {note}")
        rows.append((arm, name, res.score, d["raw_mean_jsd"], d["fisher_p"], truth_sub))

    # ---- interpretation ----
    print("\n" + "=" * 78)
    score_of = {r[0]: r[2] for r in rows}
    print(f"Threshold (frozen on calibration, FPR<={conformal_fpr:.1%}): {threshold:+.4f}")

    def verdict(arm: str, expect_detect: bool) -> str:
        s = score_of.get(arm)
        if s is None:
            return "uninformative"
        detected = s > threshold
        if expect_detect:
            return "DETECTED" if detected else "MISSED"
        return "false positive" if detected else "correctly clean"

    print(f"\n  A1 full substitution   -> {verdict('A1', True)}")
    print(f"  A3 dilution (eps=0.10) -> {verdict('A3', True)}")
    print(f"  A5 probe-aware evasion -> {verdict('A5', True)}   <- the novel attack")
    print(f"  A10 canary-aware       -> {verdict('A10', True)}   <- the novel attack")
    print(f"  A4 sampler retune      -> {verdict('A4', False)}   <- specificity test")
    print(f"  A11 benign routing     -> {verdict('A11', False)}   <- THE CONFOUND")
    print(f"  A0 honest control      -> {verdict('A0', False)}   "
          f"(and {emp_fpr:.1%} FPR over {N_HOLDOUT} holdout sessions)")

    print("\nInterpretation:")
    if score_of.get("A5") is not None and score_of["A5"] <= threshold:
        print("  * A5 defeats OTE completely. The gateway serves the honest model to")
        print("    anything probe-shaped, and OTE's probes are the most probe-shaped")
        print("    traffic imaginable. No source paper evaluates this attack.")
    if (score_of.get("A4") is not None and score_of.get("A1") is not None
            and score_of["A4"] > score_of["A1"]):
        print("  * SPECIFICITY FAILURE: A4 (sampler retune, GENUINE weights) scores")
        print(f"    {score_of['A4']:+.3f} vs A1 (real substitution) {score_of['A1']:+.3f}. OTE flags")
        print("    a temperature change HARDER than an actual model swap - it detects")
        print("    'the distribution moved', not 'the model changed'. IRIS declares")
        print("    this case out of scope, so nobody has measured it until now.")
    if score_of.get("A3") is not None and score_of["A3"] <= threshold:
        print("  * A3 (eps=0.10) is missed at this budget, as IRIS's Theta(1/eps)")
        print("    query complexity predicts. Detecting it needs more probes, which")
        print("    is exactly the cost the break-even analysis prices.")
    if score_of.get("A6") is not None and score_of["A6"] > score_of.get("A1", 0):
        print("  * A6 (cache replay) scores highest of all - but for the WRONG reason:")
        print("    caching collapses the answer distribution to a point mass. OTE is")
        print("    detecting determinism, not substitution.")
    if score_of.get("A11") is not None and score_of["A11"] <= threshold:
        print("  * A11 is NOT flagged here, because this mock's alternate provider is")
        print("    near-identical to genuine. How severe the confound really is depends")
        print("    on how much real providers of the same model differ - an empirical")
        print("    question the live census answers, not the simulator.")
    if score_of.get("A2") is not None and score_of["A2"] <= threshold:
        print("  * A2 is missed, and unavoidably so: it routes to the SAME backend as")
        print("    A11 while carrying the opposite ground-truth label. No behavioural")
        print("    auditor can separate two arms whose responses are drawn from one")
        print("    distribution - that is a ceiling on the taxonomy, not on OTE.")

    # Write the deliverable table.
    out = ROOT / "results" / "tables" / "ote_arms.md"
    lines = [
        "# OTE-lite vs the 12 adversary arms (mock backend)\n",
        f"Probes: {len(probes)} cells x {REPEATS} repeats = {len(probes)*REPEATS} per arm.\n",
        "Statistic is the **permutation-debiased** mean Jensen-Shannon divergence "
        f"({auditor.n_perm} permutations per cell). The plug-in JSD it corrects is "
        "upward-biased at 30 samples/cell - it scored honest-vs-honest at 0.1755, "
        "above four of the twelve arms. `raw` is the uncorrected statistic, kept "
        "because it is what Bruckner thresholds.\n",
        f"Threshold: the maximum over **{N_CALIB} independent honest calibration "
        f"sessions** = **{threshold:+.4f}**. Under exchangeability that is a "
        f"conformal FPR bound of 1/{N_CALIB+1} = {conformal_fpr:.2%}. Measured on "
        f"**{N_HOLDOUT} disjoint holdout sessions**: realised FPR "
        f"**{len(false_pos)}/{len(holdout)} = {emp_fpr:.1%}**.\n",
        "| Arm | Name | Debiased JSD | raw JSD | Fisher p | vs threshold | True substitution rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm, name, score, raw, p, truth in rows:
        if score is None:
            lines.append(f"| {arm} | {name} | uninformative | - | - | - | {truth}/{len(probes)*REPEATS} |")
        else:
            flag = "**FLAGGED**" if score > threshold else "clean"
            lines.append(
                f"| {arm} | {name} | {score:+.4f} | {raw:.4f} | {p:.1e} | {flag} "
                f"| {truth}/{len(probes)*REPEATS} |"
            )
    lines += [
        "",
        "## Footnotes",
        "",
        "**A2 and A11 route to the same backend under opposite labels.** Both serve "
        "`alternate-70b`; A2 is labelled substitution (the deployment differs) and A11 "
        "is labelled genuine (the weights are correct). Their responses are therefore "
        "draws from one distribution, and *no* behavioural auditor can separate them. "
        "This is a deliberate ceiling in the taxonomy, not a defect in any method - "
        "and it is the sharpest form of the confound in idea.md section 5. Pooling A2 "
        "with A11 in a ROC curve caps AUROC below 1 by construction; the evaluation "
        "grid must report them separately.",
        "",
        "**The Fisher p-value combines per-cell permutation p-values** across the "
        "8 cells. Cells are independently sampled prompts, so the independence "
        "assumption holds by construction here - which is also why Bruckner's battery "
        "gains power by adding cells rather than repeats.",
        "",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT)}  ({time.perf_counter()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
