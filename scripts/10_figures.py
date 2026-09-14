"""Phase 7 - the six figures, from committed results only. No API key, no fitting.

  F1  dollars-to-detection      power vs imputed audit spend, per auditor
  F2  break-even                adversary savings vs audit cost across eps
  F3  applicability coverage    which auditors can run on the free-tier fleet
  F4  evasion degradation       AUROC heatmap, auditors x arms
  F5  sealed vs fresh blocks    realised FPR of each sealed threshold
  F6  the confound              A3 (fraud) vs A11 (benign routing) score overlap

Inputs (each figure is skipped, with a message, if its input is missing):
  results/grid.jsonl                      07_grid.py
  results/eps_power.jsonl + _meta.json    09_eps_power.py
  results/threshold_audit.json            08_threshold_audit.py
  results/tables/coverage.md              01_limits.py

Every figure has a table twin in results/tables/, so no value is readable only
from a picture. Economics numbers go to results/tables/economics.md.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
FIG = RES / "figures"
TABLES = RES / "tables"

# ---- palette: validated reference instance, light surface -------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]

# Colour follows the auditor, in fixed slot order, identically in every figure.
AUDITORS = ["OTE", "IRIS-lite", "GATEOPS", "KBF", "BENCH", "FUSE"]
COLOR = dict(zip(AUDITORS, SERIES))
ARMS = [f"A{i}" for i in range(1, 12)]
GENUINE_ARMS = {"A4", "A11"}
THRESH_FUSE_LOG10 = 2.0          # FUSE flags at e >= 100; its score is log10(e)

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10,
    "text.color": INK, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2,
    "ytick.labelcolor": INK_2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "lines.linewidth": 2.0, "lines.markersize": 6, "legend.frameon": False,
    "axes.titlesize": 11, "axes.titleweight": "semibold", "axes.titlelocation": "left",
})


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def scores(rows, auditor):
    return [r["auditors"][auditor]["score"] for r in rows
            if auditor in r["auditors"] and r["auditors"][auditor]["applicable"]
            and r["auditors"][auditor]["score"] is not None]


def flagged_rate(rows, auditor):
    cells = [r["auditors"][auditor] for r in rows if auditor in r["auditors"]]
    cells = [c for c in cells if c["applicable"]]
    if not cells:
        return None
    return sum(c["decision"] == "inconsistent" for c in cells) / len(cells)


def auroc(pos, neg):
    """P(score from pos > score from neg), ties counted half. Mann-Whitney form."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def sessions_for_power(p, target=0.8):
    """Independent sessions, flag if any flags, needed to reach `target` power."""
    if p is None or p <= 0:
        return math.inf
    if p >= 1:
        return 1
    return math.ceil(math.log(1 - target) / math.log(1 - p))


def rule_of_three_upper(n):
    """Exact one-sided 95% upper bound on p after 0 successes in n trials."""
    return 1 - 0.05 ** (1 / n)


FAMILY_FPR_BUDGET = 0.05


def max_admissible_sessions(f, budget=FAMILY_FPR_BUDGET):
    """Most sessions an any-flag audit can run before 1-(1-f)^k exceeds the budget.

    Repeating an audit buys power and false positives at the same time. An
    auditor that reaches 80% power only by running more sessions than its
    false-positive budget allows has not detected anything - it has flagged.
    """
    if f <= 0:
        return math.inf
    if f >= budget:
        return 1 if f <= budget else 0
    return math.floor(math.log(1 - budget) / math.log(1 - f))


def honest_fpr(grid, audit):
    """Pooled realised per-session FPR on honest sessions never used for fitting.

    Blocks B and C from 08_threshold_audit.py plus the 07_grid.py holdout, floored
    at the conformal 1/(N+1): an auditor with no observed false positive in a few
    hundred sessions is not thereby shown to have none.
    """
    holdout = [r for r in grid if r["split"] == "holdout"]
    out = {}
    for a in AUDITORS:
        cells = [r["auditors"][a] for r in holdout
                 if a in r["auditors"] and r["auditors"][a]["applicable"]]
        k = sum(c["decision"] == "inconsistent" for c in cells)
        n = len(cells)
        for rec in (audit or {}).get("rows", []):
            if rec["auditor"] != a:
                continue
            for label, b in rec["blocks"].items():
                if not label.startswith("sealed"):
                    k += round(b["tail_above_threshold"] * b["n"])
                    n += b["n"]
        floor = 1 / 101
        out[a] = (max(k / n, floor) if n else floor, k, n)
    return out


def session_price_ratio(meta):
    """Substitute/genuine cost of one session's token mix (mock ladder prices)."""
    import yaml
    prices = yaml.safe_load((ROOT / "config" / "prices.yaml").read_text(encoding="utf-8"))["endpoints"]
    tin, tout = meta["prompt_tokens_per_session"], meta["completion_tokens_per_session"]

    def cost(p):
        return tin * p["input_per_mtok"] + tout * p["output_per_mtok"]

    return cost(prices["mock:substitute-8b"]) / cost(prices["mock:genuine-70b"])


def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote results/figures/{name}.png")


def thresholds():
    import yaml
    doc = yaml.safe_load((ROOT / "config" / "protocol.yaml").read_text(encoding="utf-8"))
    out = {k: (v or {}).get("threshold") for k, v in doc["thresholds"].items()}
    out["FUSE"] = THRESH_FUSE_LOG10
    return out, doc


# ---------------------------------------------------------------------------
def power_table(eps_rows):
    """{eps: {auditor: (power, n)}} from the dense sweep (A3 only)."""
    out = {}
    for eps in sorted({r["eps"] for r in eps_rows if r["arm"] == "A3"}):
        batch = [r for r in eps_rows if r["arm"] == "A3" and r["eps"] == eps]
        out[eps] = {a: (flagged_rate(batch, a), len(batch)) for a in AUDITORS}
    return out


def session_costs(eps_rows):
    return {a: next(r["auditors"][a]["cost_usd"] for r in eps_rows if a in r["auditors"])
            for a in AUDITORS}


def f1_dollars_to_detection(eps_rows, fpr):
    if not eps_rows:
        return print("  F1 skipped: run scripts/09_eps_power.py")
    power = power_table(eps_rows)
    cost = session_costs(eps_rows)
    facets = [e for e in (0.05, 0.10, 0.25) if e in power]
    fig, axes = plt.subplots(1, len(facets), figsize=(4.2 * len(facets), 3.8), sharey=True)
    axes = list(axes) if len(facets) > 1 else [axes]
    for ax, eps in zip(axes, facets):
        missing = []
        for a in AUDITORS:
            p, n = power[eps][a]
            if not p:
                missing.append(a)
                continue
            kmax = max_admissible_sessions(fpr[a][0])
            ks = list(range(1, 401))
            ok = [k for k in ks if k <= kmax]
            bad = [k for k in ks if k > kmax]
            if ok:
                ax.plot([k * cost[a] for k in ok], [1 - (1 - p) ** k for k in ok],
                        color=COLOR[a], label=a)
            if bad:
                seg = ([ok[-1]] if ok else []) + bad
                ax.plot([k * cost[a] for k in seg], [1 - (1 - p) ** k for k in seg],
                        color=COLOR[a], alpha=0.25, lw=1.5, label=None if ok else a)
        ax.axhline(0.8, color=AXIS, lw=0.8)
        ax.set_xscale("log")
        ax.set_ylim(0, 1.02)
        ax.set_title(f"A3 dilution, eps = {eps:g}")
        ax.set_xlabel("imputed audit spend (USD, log)")
        if missing:
            ax.text(0.02, 0.96, "never detected in 20 sessions:\n" + ", ".join(missing),
                    transform=ax.transAxes, va="top", fontsize=8, color=INK_2)
    axes[0].set_ylabel("power (any session flags)")
    # Solid proxies: an auditor whose whole curve is inadmissible still gets a
    # legible swatch; faintness is explained in the footnote, not the legend.
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=COLOR[a]) for a in AUDITORS]
    fig.legend(handles, AUDITORS, loc="lower center", ncol=len(AUDITORS), bbox_to_anchor=(0.5, -0.06))
    fig.suptitle("F1  Dollars to detection: what it costs to catch a diluting gateway",
                 x=0.01, ha="left", fontsize=12, fontweight="semibold")
    fig.text(0.01, -0.1, f"Faint: beyond this spend the audit's family false-positive rate exceeds "
             f"{FAMILY_FPR_BUDGET:.0%} (realised per-session honest FPR, pooled). "
             f"Table twin: results/tables/economics.md", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    save(fig, "F1_dollars_to_detection")


def f2_break_even(eps_rows, meta, fpr, monthly_spend=1000.0):
    if not eps_rows or not meta:
        return print("  F2 skipped: run scripts/09_eps_power.py")
    power = power_table(eps_rows)
    cost = session_costs(eps_rows)
    ratio = session_price_ratio(meta)
    eps_grid = sorted(power)
    fine = [10 ** (math.log10(eps_grid[0]) + i * (math.log10(eps_grid[-1]) - math.log10(eps_grid[0])) / 60)
            for i in range(61)]
    savings = lambda e: monthly_spend * e * (1 - ratio)  # noqa: E731

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    ax.plot(fine, [savings(e) for e in fine], color=INK, lw=2.4)
    mid = fine[len(fine) // 2]
    ax.annotate("adversary's monthly saving on a $1,000/month account",
                (mid, savings(mid)), xytext=(0, -14), textcoords="offset points",
                ha="left", va="top", fontsize=9, color=INK)

    rows_md = []
    best_cost = {}
    for a in AUDITORS:
        kmax = max_admissible_sessions(fpr[a][0])
        xs, ys, lx, ly, bx, by = [], [], [], [], [], []
        for eps in eps_grid:
            p, n = power[eps][a]
            k = sessions_for_power(p)
            if math.isinf(k):
                lb = sessions_for_power(rule_of_three_upper(n)) * cost[a]
                lx.append(eps)
                ly.append(lb)
                rows_md.append((a, eps, p, None, lb, None))
            elif k <= kmax:
                xs.append(eps)
                ys.append(k * cost[a])
                rows_md.append((a, eps, p, k * cost[a], None, True))
                best_cost[eps] = min(best_cost.get(eps, math.inf), k * cost[a])
            else:
                bx.append(eps)
                by.append(k * cost[a])
                rows_md.append((a, eps, p, k * cost[a], None, False))
        if xs:
            ax.plot(xs, ys, color=COLOR[a], marker="o", markeredgecolor=SURFACE,
                    markeredgewidth=1.2, label=a)
        if bx:
            ax.scatter(bx, by, marker="x", color=COLOR[a], lw=1.4, s=42,
                       label=None if xs else a)
        if lx:
            ax.scatter(lx, ly, marker="^", facecolors="none", edgecolors=COLOR[a], lw=1.4, s=42)

    # eps*: smallest swept eps at which the cheapest auditor reaching 80% power
    # costs no more than the adversary saves. Below it, catching is not worth it.
    affordable = [e for e in eps_grid if best_cost.get(e, math.inf) <= savings(e)]
    eps_star = min(affordable) if affordable else None
    if eps_star is not None:
        ax.axvspan(eps_grid[0] * 0.9, eps_star, color=GRID, alpha=0.6, lw=0, zorder=0)
    ax.scatter([], [], marker="^", facecolors="none", edgecolors=INK_2,
               label="lower bound (0 of 20 detected)")
    ax.scatter([], [], marker="x", color=INK_2,
               label=f"reaches 80% only past a {FAMILY_FPR_BUDGET:.0%} family FPR")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(eps_grid)
    ax.set_xticklabels([f"{e:g}" for e in eps_grid])
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_xlim(eps_grid[0] * 0.9, eps_grid[-1] * 1.1)
    ax.set_xlabel("dilution rate eps (fraction of requests served by the cheaper model, log)")
    ax.set_ylabel("USD per month (log)")
    title = "F2  Break-even: audit cost to reach 80% power vs what the adversary saves"
    ax.set_title(title, fontsize=12)
    if eps_star is not None:
        ax.text(0.01, 0.97, f"shaded: swept eps below eps* = {eps_star:g}, where no admissible audit pays for itself",
                transform=ax.transAxes, va="top", fontsize=8.5, color=INK_2)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8.5)
    fig.tight_layout()
    save(fig, "F2_break_even")

    md = [
        "# Economics: audit cost to 80% power vs adversary savings\n",
        f"Protocol `{meta['protocol_sha256'][:16]}...`. Power per session is the fraction of "
        f"20 A3 sessions each auditor flags under the SEALED threshold (09_eps_power.py). "
        f"Sessions needed = smallest k with 1-(1-p)^k >= 0.8, flagging if any session flags; "
        f"repeating an audit inflates its false-positive rate too, which the admissibility rule below accounts for.\n",
        f"Substitute/genuine price ratio for the session token mix: **{ratio:.3f}**. "
        f"Adversary saving = ${monthly_spend:,.0f} x eps x (1 - ratio) per month.\n",
        f"An audit is **admissible** only if its family false-positive rate "
        f"1-(1-f)^k stays within {FAMILY_FPR_BUDGET:.0%}, where f is the auditor's realised "
        f"per-session FPR on honest sessions never used for fitting (threshold-audit blocks "
        f"B and C plus the grid holdout), floored at 1/101.\n",
        "| Auditor | honest flags | honest sessions | f used | max admissible sessions |",
        "|---|---|---|---|---|",
    ]
    for a in AUDITORS:
        f, k, n = fpr[a]
        km = max_admissible_sessions(f)
        md.append(f"| {a} | {k} | {n} | {f:.2%} | {'unbounded' if math.isinf(km) else km} |")
    md += [
        "",
        f"eps* (smallest swept rate where the cheapest ADMISSIBLE audit pays for itself): "
        f"**{eps_star if eps_star is not None else 'not reached in sweep'}**\n",
        "| Auditor | eps | power/session | audit cost to 80% (USD) | admissible | saving (USD) |",
        "|---|---|---|---|---|---|",
    ]
    for a, eps, p, c, lb, ok in rows_md:
        if c is None:
            cell, verdict = f">= {lb:.3f} (0/20 detected)", "-"
        else:
            cell, verdict = f"{c:.3f}", "yes" if ok else "no"
        md.append(f"| {a} | {eps:g} | {p:.0%} | {cell} | {verdict} | {savings(eps):.2f} |")
    (TABLES / "economics.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("  wrote results/tables/economics.md")


def f3_coverage():
    path = TABLES / "coverage.md"
    if not path.exists():
        return print("  F3 skipped: run scripts/01_limits.py")
    text = path.read_text(encoding="utf-8")
    section = text.split("## Auditor applicability", 1)[-1].split("##", 1)[0]
    rows = []
    for line in section.splitlines():
        m = re.match(r"\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\d+)/(\d+)\s*\|\s*(\d+)%", line)
        if m and not m.group(1).startswith("("):
            rows.append((m.group(1).replace("`", ""), int(m.group(3)), int(m.group(4))))
    rows.sort(key=lambda r: r[1] / r[2])
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ys = range(len(rows))
    fr = [r[1] / r[2] for r in rows]
    ax.barh(list(ys), fr, height=0.62, color=SERIES[0])
    for y, (name, k, n) in zip(ys, rows):
        ax.text(k / n + 0.01, y, f"{k}/{n}", va="center", fontsize=9, color=INK_2)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlim(0, 1.12)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("share of working free-tier endpoints where the auditor can run")
    ax.set_title("F3  Applicability coverage: RUT runs nowhere; OTE-as-published on a third", fontsize=12)
    fig.tight_layout()
    save(fig, "F3_coverage")


def f4_evasion_heatmap(grid):
    if not grid:
        return print("  F4 skipped: run scripts/07_grid.py")
    honest = [r for r in grid if r["split"] == "holdout"]
    rows = AUDITORS[:5] + ["RUT", "FUSE"]
    mat = []
    for a in rows:
        line = []
        for arm in ARMS:
            arm_rows = [r for r in grid if r["split"] == "arms" and r["arm"] == arm]
            line.append(auroc(scores(arm_rows, a), scores(honest, a)))
        mat.append(line)

    cmap = LinearSegmentedColormap.from_list(
        "seq_blue", ["#f0efec", "#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95"])
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    ax.grid(False)
    for i, line in enumerate(mat):
        for j, v in enumerate(line):
            if v is None:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, facecolor=SURFACE,
                                           edgecolor=GRID, lw=0.6))
                ax.text(j, i, "n/a", ha="center", va="center", fontsize=8, color=MUTED)
                continue
            t = max(0.0, min(1.0, (v - 0.5) / 0.5))
            ax.add_patch(plt.Rectangle((j - 0.48, i - 0.48), 0.96, 0.96,
                                       facecolor=cmap(t), edgecolor=SURFACE, lw=1))
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                    color="#ffffff" if t > 0.6 else INK)
    ax.set_xlim(-0.5, len(ARMS) - 0.5)
    ax.set_ylim(len(rows) - 0.5, -0.5)
    ax.set_xticks(range(len(ARMS)))
    ax.set_xticklabels([f"{a}\ngenuine" if a in GENUINE_ARMS else a for a in ARMS])
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0.5, 1.0))
    cb = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("AUROC vs 50 honest holdout sessions", color=INK_2)
    cb.outline.set_visible(False)
    ax.set_title("F4  Evasion degradation: A5 (probe-aware) sits at chance for every auditor.\n"
                 "In genuine columns a high value is a false-positive risk, not a success.",
                 fontsize=11)
    fig.text(0.01, -0.02, "Each arm cell uses 3 sessions (07_grid.py); values are coarse. "
             "Table twin: results/tables/grid.md", fontsize=8, color=MUTED)
    fig.tight_layout()
    save(fig, "F4_evasion_auroc")


def f5_sealed_vs_fresh(grid, audit):
    if not audit or not grid:
        return print("  F5 skipped: run scripts/08_threshold_audit.py and 07_grid.py")
    thr, doc = thresholds()
    bound = doc.get("conformal_fpr_bound", 0.0099)
    holdout = [r for r in grid if r["split"] == "holdout"]
    names = [r["auditor"] for r in audit["rows"]] + ["FUSE"]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    # The conformal bound is for a fresh score STRICTLY above the calibration max,
    # which is what 08_threshold_audit.py counts. 07_grid.py flags at >=, so a
    # holdout score that ties the max on a discrete statistic is flagged there.
    # Both are shown; the decision rule was not changed after the holdout.
    for y, rec in enumerate(audit["rows"]):
        a = rec["auditor"]
        blocks = rec["blocks"]
        sealed = [v["tail_above_threshold"] for k, v in blocks.items() if k.startswith("sealed")]
        fresh = [v["tail_above_threshold"] for k, v in blocks.items() if not k.startswith("sealed")]
        hs = scores(holdout, a)
        strict = sum(s > thr[a] for s in hs) / len(hs)
        as_run = flagged_rate(holdout, a)
        fresh.append(strict)
        # Offset the two series so a shared 0% does not hide one under the other.
        ax.scatter(sealed, [y - 0.14] * len(sealed), s=56, color=SERIES[0], edgecolor=SURFACE, lw=1.5,
                   zorder=3, label="sealed calibration block" if y == 0 else None)
        ax.scatter(fresh, [y + 0.14] * len(fresh), s=56, color=SERIES[1], edgecolor=SURFACE, lw=1.5,
                   zorder=3, label="fresh honest blocks + holdout (score > max)" if y == 0 else None)
        if as_run != strict:
            ax.scatter([as_run], [y + 0.14], s=56, marker="D", facecolors="none", edgecolors=INK_2, lw=1.2,
                       zorder=4, label="holdout as run by 07_grid (score >= max)")
    y = len(audit["rows"])
    ax.scatter([flagged_rate(holdout, "FUSE")], [y + 0.14], s=56, color=SERIES[1], edgecolor=SURFACE,
               lw=1.5, zorder=3)
    h, l = ax.get_legend_handles_labels()
    uniq = dict(zip(l, h))
    ax.axvline(bound, color=INK_2, lw=1)
    ax.text(bound, len(names) - 0.55, f" claimed bound {bound:.2%}", fontsize=8.5, color=INK_2, va="bottom")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.set_ylim(len(names) - 0.5, -0.5)
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("realised false-positive rate of the sealed threshold")
    ax.set_title("F5  Sealed vs fresh: discrete statistics leak past a conformal maximum", fontsize=12)
    ax.legend(uniq.values(), uniq.keys(), loc="lower right", fontsize=8.5)
    fig.text(0.01, -0.02, "Table twin: results/tables/threshold_audit.md", fontsize=8, color=MUTED)
    fig.tight_layout()
    save(fig, "F5_sealed_vs_fresh")


def f6_confound(grid, eps_rows):
    thr, _ = thresholds()
    honest = [r for r in grid if r["split"] == "holdout"]
    if eps_rows:
        a3 = [r for r in eps_rows if r["arm"] == "A3" and r["eps"] == 0.10]
        a11 = [r for r in eps_rows if r["arm"] == "A11"]
        src = "20 sessions each (09_eps_power.py)"
    else:
        a3 = [r for r in grid if r["split"] == "eps_sweep" and r.get("eps") == 0.10]
        a11 = [r for r in grid if r["split"] == "arms" and r["arm"] == "A11"]
        src = "grid sessions only (run 09_eps_power.py for 20 each)"
    if not (honest and a3 and a11):
        return print("  F6 skipped: no grid data")
    import random
    rng = random.Random(0)
    fig, axes = plt.subplots(2, 3, figsize=(10, 6))
    groups = [("honest A0", honest, MUTED), ("A3 fraud, eps=0.10", a3, SERIES[1]),
              ("A11 benign routing", a11, SERIES[0])]
    md = ["# The confound, quantified: A3 @ eps=0.10 vs A11\n",
          f"Source: {src}. AUROC(A3 vs A11) of 0.5 means the auditor cannot tell fraud "
          f"from sanctioned routing; 1.0 means it separates them perfectly.\n",
          "| Auditor | flag rate A3 | flag rate A11 | AUROC A3 vs A11 |", "|---|---|---|---|"]
    for ax, a in zip(axes.flat, AUDITORS):
        for x, (label, rows, color) in enumerate(groups):
            s = scores(rows, a)
            ax.scatter([x + rng.uniform(-0.18, 0.18) for _ in s], s, s=22, color=color,
                       edgecolor=SURFACE, lw=0.8, label=label, zorder=3)
        if thr.get(a) is not None:
            ax.axhline(thr[a], color=INK_2, lw=1)
        sep = auroc(scores(a3, a), scores(a11, a))
        ax.set_title(f"{a}   AUROC A3 vs A11 = {sep:.2f}" if sep is not None else a, fontsize=10)
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels(["A0", "A3", "A11"])
        ax.grid(axis="x", visible=False)
        md.append(f"| {a} | {flagged_rate(a3, a):.0%} | {flagged_rate(a11, a):.0%} | "
                  f"{sep:.2f} |" if sep is not None else f"| {a} | - | - | - |")
    axes.flat[0].set_ylabel("auditor score")
    axes.flat[3].set_ylabel("auditor score")
    h, l = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("F6  The confound: diluting fraud and sanctioned routing, as each auditor sees them"
                 "  (line = sealed threshold)", x=0.01, ha="left", fontsize=12, fontweight="semibold")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    save(fig, "F6_confound")
    (TABLES / "confound.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("  wrote results/tables/confound.md")


def main() -> int:
    grid = load_jsonl(RES / "grid.jsonl")
    eps_rows = load_jsonl(RES / "eps_power.jsonl")
    meta_p = RES / "eps_power_meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else None
    audit_p = RES / "threshold_audit.json"
    audit = json.loads(audit_p.read_text(encoding="utf-8")) if audit_p.exists() else None

    fpr = honest_fpr(grid, audit)

    print("Phase 7 - figures")
    f1_dollars_to_detection(eps_rows, fpr)
    f2_break_even(eps_rows, meta, fpr)
    f3_coverage()
    f4_evasion_heatmap(grid)
    f5_sealed_vs_fresh(grid, audit)
    f6_confound(grid, eps_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
