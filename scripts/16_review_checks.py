"""Post-hoc checks raised by the skeptical review (paper/REVIEW_skeptical.md).

EXPLORATORY, NOT SEALED. Everything here was decided after the v2 evaluation ran,
reads only the committed v2 sessions, and never changes a sealed number. It
answers four questions a reviewer asked:

  1. Sensitivity of eps* to the analysis choices protocol v2 sealed without
     varying them: the power target, the family false-alarm budget, and the
     substitute/genuine price ratio. Includes "no false-alarm cap at all", which
     tests the claim that false alarms, not cost, set eps*.
  2. The gpt-oss price ratio. The sealed economics priced the mock ladder at
     Cerebras Llama 70B / 8B list prices (ratio 0.115); the real census and live
     run use gpt-oss-120b / 20b, which Groq prices at exactly 2:1.
  3. FUSE under arbitrary dependence. The product of e-values assumes the
     channels are independent; the mean of e-values does not. Both are
     recomputed from the per-channel p-values stored in every session.
  4. Bootstrap confidence intervals for the grid AUROCs (30 sessions per arm).

    python scripts/16_review_checks.py

Output: results/v2/tables/review_checks.md
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arena.evalue import p_to_e  # noqa: E402
from arena.protocol import load_sealed  # noqa: E402

_spec = importlib.util.spec_from_file_location("paper15", ROOT / "scripts" / "15_paper.py")
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

OUT = P.TAB / "review_checks.md"
CHANNELS = ["OTE", "IRIS-lite", "GATEOPS", "KBF", "BENCH", "RUT"]
KAPPA = 0.5          # the calibrator FUSE uses (arena/auditors/fuse.py)
B_AUC = 1000


# ---------------------------------------------------------------- 1-2 economics
def gptoss_ratio(tokens: dict) -> float:
    prices = yaml.safe_load((ROOT / "config" / "prices.yaml").read_text())["endpoints"]
    g, s = prices["groq:openai/gpt-oss-120b"], prices["groq:openai/gpt-oss-20b"]
    tin, tout = tokens["prompt_tokens"], tokens["completion_tokens"]
    cost = lambda p: tin * p["input_per_mtok"] + tout * p["output_per_mtok"]
    return cost(s) / cost(g)


def admissible(f: float, budget: float | None) -> float:
    return math.inf if budget is None else P.max_admissible(f, budget)


def eps_star(ev, ladder, *, target, budget, ratio, exclude=()):
    """The sealed eps* rule with its three free parameters exposed.
    budget=None removes the false-alarm cap (unlimited repeats)."""
    A = ev.p["analysis"]
    floor = ev.p["calibration"]["marginal_fpr_bound"]
    grid = ev.p["evaluation"]["eps_sweep"]["eps"]
    hold = ev.sel(ladder, "holdout")
    batches = {e: ev.sel(ladder, "eps", "A3", e) for e in grid}
    cost = {n: float(np.median([r["auditors"][n]["cost_usd"] for r in batches[grid[0]]]))
            for n in P.AUD}
    f = {n: max(np.mean([r["flag"][n] for r in hold if r["app"][n]]), floor) for n in P.AUD}
    for e in grid:
        save = A["monthly_spend_usd"] * e * (1 - ratio)
        best = None
        for n in [a for a in P.AUD if a not in exclude]:
            p = np.mean([r["flag"][n] for r in batches[e]])
            k = P.sessions_for_power(p, target)
            if math.isinf(k) or k > admissible(f[n], budget):
                continue
            c = k * cost[n]
            if c <= save and (best is None or c < best[2]):
                best = (n, k, c, p)
        if best:
            return e, best, save
    return None, None, None


# ---------------------------------------------------------------- 3 FUSE
def fuse_evalues(row) -> tuple[float, float]:
    es = []
    for n in CHANNELS:
        a = row["auditors"][n]
        p = a.get("p_value") if a.get("applicable") else None
        es.append(1.0 if p is None or p != p else p_to_e(float(p), KAPPA))
    return math.prod(es), sum(es) / len(es)


# ---------------------------------------------------------------- 4 AUROC CIs
def auroc_ci(pos, neg, rng) -> tuple[float, float, float] | None:
    if not pos or not neg:
        return None
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)

    def auc(a, b):
        gt = (a[:, None] > b[None, :]).mean()
        eq = (a[:, None] == b[None, :]).mean()
        return gt + 0.5 * eq

    point = auc(pos, neg)
    boots = [auc(pos[rng.integers(0, len(pos), len(pos))], neg[rng.integers(0, len(neg), len(neg))])
             for _ in range(B_AUC)]
    return point, float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def main() -> int:
    protocol = load_sealed(ROOT / "config" / "protocol_v2.yaml")
    rows = [r for r in P.load_jsonl(P.V2 / "sessions.jsonl") if r["protocol_sha256"] == protocol["sha256"]]
    ev = P.Evidence(protocol, rows)
    A = protocol["analysis"]
    ladders = protocol["conditions"]["ladders"]
    L = ["# Post-hoc review checks (exploratory, NOT sealed)", "",
         f"Protocol v2 `{protocol['sha256'][:16]}...`; {len(rows)} committed sessions; generated by "
         "`scripts/16_review_checks.py`. Nothing here changes a sealed number.", ""]

    # 2. price ratios
    tokens = P.token_price_ratio("mock")
    r_mock, r_oss = tokens["ratio"], gptoss_ratio(tokens)
    L += ["## Price ratio", "",
          f"Session token mix: {tokens['prompt_tokens']:.0f} prompt + {tokens['completion_tokens']:.0f} "
          "completion tokens.", "",
          "| pair | prices (USD / M tokens, in / out) | substitute / genuine |", "|---|---|---|",
          f"| sealed mock ladder (Cerebras Llama 3.3 70B / 3.1 8B) | 0.85 / 1.20 vs 0.10 / 0.10 | {r_mock:.3f} |",
          f"| gpt-oss-120b / 20b on Groq (the real models) | 0.15 / 0.60 vs 0.075 / 0.30 | {r_oss:.3f} |", "",
          f"Saving per $1,000 at eps = 0.10: ${1000 * 0.10 * (1 - r_mock):.2f} (mock ratio) vs "
          f"${1000 * 0.10 * (1 - r_oss):.2f} (gpt-oss ratio); at eps = 0.05: "
          f"${1000 * 0.05 * (1 - r_mock):.2f} vs ${1000 * 0.05 * (1 - r_oss):.2f}.", ""]

    # 1. sensitivity
    print("Sensitivity of eps*")
    L += ["## Sensitivity of eps*", "",
          f"Sealed choice in bold: power target {A['power_target']:.0%}, family false-alarm budget "
          f"{A['family_fpr_budget']:.0%}, price ratio {r_mock:.3f}. 'none' = no false-alarm cap "
          "(unlimited repeats). Cells: eps* (winning auditor, sessions).", ""]
    targets, budgets = [0.5, 0.8, 0.9], [0.01, 0.05, 0.10, None]
    for lad in ladders:
        for excl, tag in [((), "all auditors"), (("IRIS-lite",), "without IRIS-lite")]:
            L += [f"### {P.LADDER_NAME[lad]}, {tag}", "",
                  "| power target \\ FPR budget | " + " | ".join(
                      ("none" if b is None else f"{b:.0%}") for b in budgets) + " |",
                  "|---|" + "---|" * len(budgets)]
            for t in targets:
                cells = []
                for b in budgets:
                    e, w, _ = eps_star(ev, lad, target=t, budget=b, ratio=r_mock, exclude=excl)
                    s = "none in sweep" if e is None else f"{e} ({w[0]}, {w[1]})"
                    if t == A["power_target"] and b == A["family_fpr_budget"]:
                        s = f"**{s}**"
                    cells.append(s)
                L.append(f"| {t:.0%} | " + " | ".join(cells) + " |")
                print(f"  {lad:<9} {tag:<18} target {t:.0%}: " + " | ".join(c.strip('*') for c in cells))
            L.append("")
        e0, w0, _ = eps_star(ev, lad, target=A["power_target"], budget=None, ratio=r_mock)
        if w0:
            hold = ev.sel(lad, "holdout")
            fk = sum(r["flag"][w0[0]] for r in hold if r["app"][w0[0]])
            fn = sum(1 for r in hold if r["app"][w0[0]])
            pk = sum(r["flag"][w0[0]] for r in ev.sel(lad, "eps", "A3", e0))
            pn = len(ev.sel(lad, "eps", "A3", e0))
            L += [f"Without a false-alarm cap the rule picks eps = {e0} with {w0[0]} over {w0[1]} "
                  f"sessions, but {w0[0]} flags {P.pct_ci(pk, pn, 1)} of those cheating sessions and "
                  f"{P.pct_ci(fk, fn, 1)} of honest ones: repetition there buys false alarms at "
                  f"almost the same rate as detections ({w0[1]} sessions give an honest customer a "
                  f"{1 - (1 - max(fk / fn, protocol['calibration']['marginal_fpr_bound'])) ** w0[1]:.0%} "
                  "chance of at least one false alarm).", ""]
        e1, w1, _ = eps_star(ev, lad, target=A["power_target"], budget=A["family_fpr_budget"], ratio=r_mock)
        e2, w2, _ = eps_star(ev, lad, target=A["power_target"], budget=A["family_fpr_budget"], ratio=r_oss)
        L += [f"Price ratio on {P.LADDER_NAME[lad]}: eps* = {e1} at {r_mock:.3f}, {e2} at {r_oss:.3f} "
              f"(audit cost at eps*: ${w1[2]:.4f} vs ${w2[2]:.4f}).", ""]

    # 3. FUSE
    print("FUSE product vs mean")
    L += ["## FUSE: product (assumes independence) vs mean (valid under any dependence)", "",
          f"Per-channel e = {KAPPA}/sqrt(p), recomputed from stored p-values; flag at e >= "
          f"{1 / protocol['alpha']:.0f}. Max |recomputed product - stored FUSE e| is reported as a "
          "consistency check.", ""]
    for lad in ladders:
        sub = [r for r in rows if r["ladder"] == lad]
        err = max(abs(math.log10(fuse_evalues(r)[0]) - math.log10(r["auditors"]["FUSE"]["e_value"]))
                  for r in sub if r["auditors"]["FUSE"]["e_value"] > 0)
        hold = ev.sel(lad, "holdout")
        mx = max(fuse_evalues(r)[1] for r in sub)
        L += [f"### {P.LADDER_NAME[lad]}", "",
              f"Consistency: max |log10 difference| = {err:.2e}. Largest mean e-value in any of the "
              f"{len(sub)} sessions: {mx:.2f} (threshold {1 / protocol['alpha']:.0f}).", "",
              "| sessions | flagged, product | flagged, mean | AUROC vs holdout, product | AUROC, mean |",
              "|---|---|---|---|---|"]
        hp = [math.log10(fuse_evalues(r)[0]) for r in hold]
        hm = [fuse_evalues(r)[1] for r in hold]
        rng = np.random.default_rng(0)
        for label, rs in [("holdout A0", hold), ("A3 eps=0.10", ev.sel(lad, "eps", "A3", 0.10)),
                          ("A3 eps=0.25", ev.sel(lad, "eps", "A3", 0.25)), ("A11", ev.sel(lad, "eps", "A11")),
                          ("A1", ev.sel(lad, "grid", "A1")), ("A5", ev.sel(lad, "grid", "A5"))]:
            prod = [fuse_evalues(r)[0] for r in rs]
            mean = [fuse_evalues(r)[1] for r in rs]
            thr = 1 / protocol["alpha"]
            kp, km = sum(p >= thr for p in prod), sum(m >= thr for m in mean)
            if label == "holdout A0":
                a1 = a2 = "-"
            else:
                a1 = f"{auroc_ci([math.log10(p) for p in prod], hp, rng)[0]:.2f}"
                a2 = f"{auroc_ci(mean, hm, rng)[0]:.2f}"
            L.append(f"| {label} | {P.pct_ci(kp, len(prod), 0)} | {P.pct_ci(km, len(mean), 0)} | {a1} | {a2} |")
        L.append("")
        print(f"  {lad}: consistency {err:.1e}, max mean e {mx:.2f}")

    # 4. AUROC CIs
    print("AUROC bootstrap intervals")
    L += ["## Grid AUROC with bootstrap 95% intervals", "",
          f"30 sessions per arm vs the 500-session holdout; {B_AUC} bootstrap replicates, seed 0. "
          "RUT is inapplicable throughout.", ""]
    for lad in ladders:
        rng = np.random.default_rng(0)
        hold = ev.sel(lad, "holdout")
        L += [f"### {P.LADDER_NAME[lad]}", "", "| Arm | " + " | ".join(P.AUD) + " |",
              "|---|" + "---|" * len(P.AUD)]
        for arm in P.ARMS[1:]:
            cells = []
            for n in P.AUD:
                ci = auroc_ci(P.Evidence.scores(ev.sel(lad, "grid", arm), n), P.Evidence.scores(hold, n), rng)
                cells.append("-" if ci is None else f"{ci[0]:.2f} [{ci[1]:.2f}, {ci[2]:.2f}]")
            L.append(f"| {arm} | " + " | ".join(cells) + " |")
            if arm == "A5":
                print(f"  {lad} A5: " + "; ".join(f"{n} {c}" for n, c in zip(P.AUD, cells)))
        L.append("")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
