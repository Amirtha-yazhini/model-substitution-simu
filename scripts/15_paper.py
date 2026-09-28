"""Paper evidence: v2 decisions, confidence intervals, figures and the numbers sheet.

Reads only committed results; fires no request and fits nothing. Every decision
is applied here from the sealed v2 thresholds (arena/protocol.decide), and every
rule used below - Wilson intervals, the admissibility budget, the eps* rule, the
bootstrap - is the one config/protocol_v2.yaml sealed before the evaluation ran.

Inputs
  results/v2/sessions.jsonl           14_evaluate_v2.py (protocol v2, both ladders)
  results/grid.jsonl, threshold_audit.json, tables/economics.md   v1, as sealed
  corpus/*.jsonl                      census, for the real-response OTE check
  results/live/*                      Phase 6 live run
  results/tables/coverage.md          01_limits.py
  config/mock_fit.yaml                12_fit_mock.py

Outputs
  paper/figures/*.pdf                 single-column (3.45 in), grayscale-safe
  results/v2/tables/*.md              table twins of every figure
  results/paper_numbers.md            every number the paper cites, with its source

    python scripts/15_paper.py
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.base import Observation  # noqa: E402
from arena.protocol import decide, load_sealed  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
V2 = RES / "v2"
TAB = V2 / "tables"
PFIG = ROOT / "paper" / "figures"
NUMBERS = RES / "paper_numbers.md"

AUD = ["OTE", "IRIS-lite", "GATEOPS", "KBF", "BENCH", "FUSE"]
ARMS = [f"A{i}" for i in range(12)]
IS_SUB = {"A0": False, "A1": True, "A2": True, "A3": True, "A4": False, "A5": True,
          "A6": True, "A7": True, "A8": True, "A9": True, "A10": True, "A11": False}
LADDER_NAME = {"mock": "hand-written mock", "mock-fit": "fitted mock"}


# ---------------------------------------------------------------- statistics
def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float, float]:
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def wilson_err(ks) -> tuple[np.ndarray, list[np.ndarray]]:
    """Point estimates and non-negative error-bar lengths for matplotlib."""
    w = np.array([wilson(k, m) for k, m in ks])
    p = w[:, 0]
    return p, [np.clip(p - w[:, 1], 0, None), np.clip(w[:, 2] - p, 0, None)]


def pct_ci(k: int, n: int, dec: int = 1) -> str:
    p, lo, hi = wilson(k, n)
    return f"{100 * p:.{dec}f}% [{100 * lo:.{dec}f}, {100 * hi:.{dec}f}]"


def auroc(pos, neg) -> float | None:
    """P(pos > neg), ties half (Mann-Whitney U / n1 n2)."""
    if not pos or not neg:
        return None
    from scipy.stats import mannwhitneyu
    return float(mannwhitneyu(pos, neg, alternative="two-sided").statistic) / (len(pos) * len(neg))


def sessions_for_power(p: float, target: float) -> float:
    if p <= 0:
        return math.inf
    if p >= 1:
        return 1
    return math.ceil(math.log(1 - target) / math.log(1 - p))


def max_admissible(f: float, budget: float) -> float:
    """Most any-flag sessions before 1-(1-f)^k exceeds the family budget."""
    if f <= 0:
        return math.inf
    if f > budget:
        return 0
    return math.floor(math.log(1 - budget) / math.log(1 - f))


# ---------------------------------------------------------------- loading
def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def score_of(a: dict, name: str) -> float | None:
    if not a.get("applicable"):
        return None
    if name == "FUSE":
        e = a.get("e_value") or 0
        return math.log10(e) if e > 0 else -99.0
    return a.get("score")


class Evidence:
    """v2 sessions with the sealed decisions applied, indexed for the analyses."""

    def __init__(self, protocol: dict, rows: list[dict]):
        self.p = protocol
        self.alpha = protocol["alpha"]
        self.rows = rows
        for r in rows:
            thr = protocol["thresholds"][r["ladder"]]
            r["flag"] = {n: decide(n, r["auditors"][n], thr, self.alpha) == "inconsistent"
                         for n in AUD}
            r["app"] = {n: bool(r["auditors"][n]["applicable"]) for n in AUD + ["RUT"]}

    def sel(self, ladder, split, arm=None, eps="any"):
        return [r for r in self.rows if r["ladder"] == ladder and r["split"] == split
                and (arm is None or r["arm"] == arm) and (eps == "any" or r.get("eps") == eps)]

    @staticmethod
    def rate(rows, name) -> tuple[int, int]:
        app = [r for r in rows if r["app"][name]]
        return sum(r["flag"][name] for r in app), len(app)

    @staticmethod
    def scores(rows, name) -> list[float]:
        return [s for r in rows if (s := score_of(r["auditors"][name], name)) is not None]


# ---------------------------------------------------------------- economics
def token_price_ratio(ladder: str) -> dict:
    """Substitute/genuine cost of one honest session's token mix, as 09 computes it."""
    from arena.runner import mock_models, run_session
    from shim.gateway import MOCK_LADDER
    from shim.ledger import load_prices

    prices = load_prices()
    ref = asyncio.run(run_session("A0", 1, V2 / "_ledger" / "ledger_paper.jsonl",
                                  models=mock_models(ladder)))
    tin = sum(float((o.usage or {}).get("prompt_tokens") or 0) for obs in ref.values() for o in obs)
    tout = sum(float((o.usage or {}).get("completion_tokens") or 0) for obs in ref.values() for o in obs)

    def cost(key):
        pr = prices.get(key, {})
        return (tin * float(pr.get("input_per_mtok", 0)) + tout * float(pr.get("output_per_mtok", 0))) / 1e6

    g, s = cost(f"mock:{MOCK_LADDER.advertised}"), cost(f"mock:{MOCK_LADDER.substitute.model}")
    return {"prompt_tokens": tin, "completion_tokens": tout, "genuine_usd": g,
            "substitute_usd": s, "ratio": s / g}


def economics(ev: Evidence, ladder: str, exclude: tuple[str, ...] = ()) -> dict:
    """The sealed eps* analysis. `exclude` exists only for the post-hoc check
    below and is empty for every sealed number."""
    A = ev.p["analysis"]
    target, budget, spend = A["power_target"], A["family_fpr_budget"], A["monthly_spend_usd"]
    floor = ev.p["calibration"]["marginal_fpr_bound"]
    eps_grid = ev.p["evaluation"]["eps_sweep"]["eps"]
    hold = ev.sel(ladder, "holdout")
    batches = {e: ev.sel(ladder, "eps", "A3", e) for e in eps_grid}
    price = token_price_ratio(ladder)
    save = {e: spend * e * (1 - price["ratio"]) for e in eps_grid}
    cost = {n: float(np.median([r["auditors"][n]["cost_usd"] for r in batches[eps_grid[0]]]))
            for n in AUD}

    H = {n: np.array([r["flag"][n] for r in hold if r["app"][n]], dtype=bool) for n in AUD}
    E = {e: {n: np.array([r["flag"][n] for r in b], dtype=bool) for n in AUD}
         for e, b in batches.items()}

    def solve(f: dict, power: dict):
        """eps* and the winning audit, by the sealed rule."""
        for e in eps_grid:
            best = None
            for n in [a for a in AUD if a not in exclude]:
                p = power[e][n]
                k = sessions_for_power(p, target)
                if math.isinf(k) or k > max_admissible(f[n], budget):
                    continue
                c = k * cost[n]
                if c <= save[e] and (best is None or c < best[2]):
                    best = (n, k, c, p)
            if best:
                return e, best
        return None, None

    f = {n: max(H[n].mean(), floor) for n in AUD}
    power = {e: {n: E[e][n].mean() for n in AUD} for e in eps_grid}
    eps_star, win = solve(f, power)

    rng = np.random.default_rng(A["eps_star_ci"]["seed"])
    B = A["eps_star_ci"]["replicates"]
    boot = []
    nh = len(hold)
    for _ in range(B):
        ih = rng.integers(0, nh, nh)
        fb = {n: max(H[n][ih].mean() if len(H[n]) == nh else H[n][rng.integers(0, len(H[n]), len(H[n]))].mean(), floor)
              for n in AUD}
        pb = {}
        for e in eps_grid:
            m = len(batches[e])
            ie = rng.integers(0, m, m)
            pb[e] = {n: E[e][n][ie].mean() for n in AUD}
        boot.append(solve(fb, pb)[0])
    finite = sorted(b for b in boot if b is not None)
    dist = {str(e): sum(1 for b in boot if b == e) / B for e in eps_grid}
    dist["none"] = sum(1 for b in boot if b is None) / B

    # Percentile interval, counting "no eps* in the sweep" as +infinity.
    lo = finite[int(0.025 * B)] if len(finite) > int(0.025 * B) else None
    hi_i = int(math.ceil(0.975 * B)) - 1
    hi = sorted(boot, key=lambda b: math.inf if b is None else b)[hi_i]
    return {"ladder": ladder, "price": price, "save": save, "cost": cost,
            "f": {n: (f[n], int(H[n].sum()), len(H[n])) for n in AUD},
            "kmax": {n: max_admissible(f[n], budget) for n in AUD},
            "power": {e: {n: (int(E[e][n].sum()), len(E[e][n])) for n in AUD} for e in eps_grid},
            "eps_star": eps_star, "winner": win,
            "boot": {"dist": dist, "lo": lo, "hi": hi, "B": B}}


# ---------------------------------------------------------------- real data
def census_ote() -> list[dict]:
    """Re-run OTE on the census recordings (REPORT §3.4), from code this time."""
    from arena.auditors.ote import OTEAuditor

    def obs(fname, keep=lambda r: True):
        out = []
        for r in load_jsonl(ROOT / "corpus" / fname):
            if not r["ok"] or not keep(r):
                continue
            out.append(Observation(probe_id=r["probe_id"], cell=r["cell"],
                                   text=r["body"]["choices"][0]["message"].get("content") or "",
                                   latency_s=r["latency_s"],
                                   system_fingerprint=r["body"].get("system_fingerprint")))
        return out

    big = "groq__openai__gpt-oss-120b.jsonl"
    ote = OTEAuditor()
    cases = [
        ("120b first half vs second half (null)",
         obs(big, lambda r: r["repeat"] >= 15), obs(big, lambda r: r["repeat"] < 15)),
        ("20b vs 120b (substitution)", obs("groq__openai__gpt-oss-20b.jsonl"), obs(big)),
        ("qwen3.8-27b vs 120b (different family)", obs("groq__qwen__qwen3.8-27b.jsonl"), obs(big)),
    ]
    out = []
    for label, s, r in cases:
        res = ote.audit(s, r)
        out.append({"case": label, "score": res.score, "fisher_p": res.detail.get("fisher_p"),
                    "n_cells": res.detail.get("n_cells"), "n_s": len(s), "n_r": len(r)})
    fps = {m: len({o.system_fingerprint for o in obs(f) if o.system_fingerprint})
           for m, f in [("120b", big), ("20b", "groq__openai__gpt-oss-20b.jsonl")]}
    n = {m: len(obs(f)) for m, f in [("120b", big), ("20b", "groq__openai__gpt-oss-20b.jsonl")]}
    from arena.auditors.iris_lite import IRISAuditor
    iris = IRISAuditor(n_estimators=100, n_splits=3)
    for (label, s, r), o in zip(cases, out):
        res = iris.audit(s, r)
        o["iris_score"] = res.score
        o["iris_p"] = float(res.detail.get("p_value", float("nan")))
        o["iris_cv_accuracy"] = float(res.detail.get("cv_accuracy", float("nan")))
    return out, fps, n


def coverage_rows() -> list[tuple[str, int, int]]:
    text = (RES / "tables" / "coverage.md").read_text(encoding="utf-8")
    section = text.split("## Auditor applicability", 1)[-1].split("##", 1)[0]
    rows = []
    for line in section.splitlines():
        m = re.match(r"\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\d+)/(\d+)\s*\|\s*(\d+)%", line)
        if m and not m.group(1).startswith("("):
            rows.append((m.group(1).replace("`", ""), int(m.group(3)), int(m.group(4))))
    return rows


def v1_evidence() -> dict:
    v1 = yaml.safe_load((ROOT / "config" / "protocol.yaml").read_text(encoding="utf-8"))
    thr = {k: (v or {}).get("threshold") for k, v in v1["thresholds"].items()}
    grid = load_jsonl(RES / "grid.jsonl")
    hold = [r for r in grid if r["split"] == "holdout"]
    audit = json.loads((RES / "threshold_audit.json").read_text(encoding="utf-8"))
    out = {"sha": v1["sha256"], "thr": thr, "holdout": {}, "fresh": {}}
    for n in AUD:
        cells = [r["auditors"][n] for r in hold if r["auditors"][n]["applicable"]]
        ge = sum(c["decision"] == "inconsistent" for c in cells)
        gt = (sum(c["score"] > thr[n] for c in cells) if n != "FUSE" else ge)
        out["holdout"][n] = {"ge": ge, "gt": gt, "n": len(cells)}
    for rec in audit["rows"]:
        k = n = 0
        for label, b in rec["blocks"].items():
            if not label.startswith("sealed"):
                k += round(b["tail_above_threshold"] * b["n"])
                n += b["n"]
        out["fresh"][rec["auditor"]] = (k, n)
    m = re.search(r"eps\*.*?\*\*([\d.]+)\*\*", (RES / "tables" / "economics.md").read_text(encoding="utf-8"))
    out["eps_star"] = float(m.group(1)) if m else None
    return out


# ---------------------------------------------------------------- figures
W = 3.45          # IEEE single column, inches
STYLE = {         # grayscale-safe: identity carried by marker + dash, not by colour
    "OTE":       dict(color="0.0",  ls="-",            marker="o", mfc="0.0"),
    "IRIS-lite": dict(color="0.35", ls="--",           marker="s", mfc="white"),
    "GATEOPS":   dict(color="0.55", ls=":",            marker="^", mfc="0.55"),
    "KBF":       dict(color="0.2",  ls="-.",           marker="D", mfc="white"),
    "BENCH":     dict(color="0.45", ls=(0, (5, 1.5)),  marker="v", mfc="0.45"),
    "FUSE":      dict(color="0.0",  ls=(0, (1, 1)),    marker="x", mfc="0.0"),
}


def setup_mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "serif",
        # Liberation Serif has Times New Roman's metrics; used where Times is absent.
        "font.serif": ["Times New Roman", "Times", "Liberation Serif", "DejaVu Serif"],
        "mathtext.fontset": "stix", "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
        "legend.fontsize": 7.5, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
        "pdf.fonttype": 42, "ps.fonttype": 42,           # embedded TrueType (PDF eXpress)
        "axes.linewidth": 0.5, "axes.edgecolor": "0.3", "axes.spines.top": False,
        "axes.spines.right": False, "axes.grid": True, "axes.axisbelow": True, "grid.color": "0.88",
        "grid.linewidth": 0.4, "lines.linewidth": 0.9, "lines.markersize": 3.2,
        "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.major.size": 2,
        "ytick.major.size": 2, "legend.frameon": False, "figure.dpi": 150,
        # Drawn at the final column width and saved at exactly that size, so LaTeX
        # places them unscaled and the fonts print at their nominal 7.5-8 pt.
        "figure.constrained_layout.use": True, "savefig.bbox": "standard",
    })
    return plt


def save(fig, name, plt):
    PFIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(PFIG / f"{name}.pdf")
    fig.savefig(PFIG / f"{name}.png", dpi=300)
    plt.close(fig)
    print(f"  wrote paper/figures/{name}.pdf")


def fig_power(plt, ev, eco):
    """Detection power per session vs dilution rate, both ladders, Wilson 95%."""
    lads = list(eco)
    fig, axes = plt.subplots(len(lads), 1, figsize=(W, 1.55 * len(lads) + 0.35), sharex=True)
    eps_grid = ev.p["evaluation"]["eps_sweep"]["eps"]
    for ax, lad in zip(axes, lads):
        E = eco[lad]
        for i, n in enumerate(AUD):
            ks = [E["power"][e][n] for e in eps_grid]
            p, err = wilson_err(ks)
            x = np.array(eps_grid) * (1 + 0.025 * (i - 2.5))      # dodge the CIs
            st = STYLE[n]
            ax.errorbar(x, p, yerr=err, color=st["color"], ls=st["ls"], marker=st["marker"],
                        mfc=st["mfc"], mec=st["color"], elinewidth=0.45, capsize=0, label=n)
        ax.axhline(0.8, color="0.5", lw=0.5)
        es = E["eps_star"]
        if es is not None:
            ax.axvline(es, color="0.0", lw=0.6, ls="-")
            b = E["boot"]
            if b["lo"] is not None:
                ax.axvspan(b["lo"], b["hi"] if b["hi"] is not None else eps_grid[-1],
                           color="0.9", lw=0, zorder=0)
            ax.text(es * 0.96, 0.93, r"$\varepsilon^*$" + f" = {es:g}", fontsize=7.5, va="top",
                    ha="right")
        ax.set_xscale("log")
        ax.set_ylim(-0.02, 1.02)
        ax.set_ylabel("power per session")
        ax.set_title(f"({'ab'[lads.index(lad)]}) {LADDER_NAME[lad]}", loc="left", pad=2)
    axes[-1].set_xticks(eps_grid)
    axes[-1].set_xticklabels([f"{e:g}" for e in eps_grid])
    axes[-1].minorticks_off()
    axes[-1].set_xlabel(r"dilution rate $\varepsilon$ (A3)")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=6, bbox_to_anchor=(0.5, 1.0), handlelength=2.2,
               columnspacing=0.8)
    fig.tight_layout(rect=(0, 0, 1, 0.95), h_pad=0.4)
    save(fig, "fig_power", plt)


def fig_break_even(plt, ev, eco, lad="mock"):
    E = eco[lad]
    A = ev.p["analysis"]
    eps_grid = ev.p["evaluation"]["eps_sweep"]["eps"]
    fig, ax = plt.subplots(figsize=(W, 2.55))
    ax.plot(eps_grid, [E["save"][e] for e in eps_grid], color="0.0", lw=1.4,
            label="cheater's saving / month")
    for n in AUD:
        st = STYLE[n]
        xa, ya, xb, yb = [], [], [], []
        for e in eps_grid:
            k, m = E["power"][e][n]
            need = sessions_for_power(k / m, A["power_target"])
            if math.isinf(need):
                continue
            (xa if need <= E["kmax"][n] else xb).append(e)
            (ya if need <= E["kmax"][n] else yb).append(need * E["cost"][n])
        if xa:
            ax.plot(xa, ya, color=st["color"], ls=st["ls"], marker=st["marker"], mfc=st["mfc"],
                    mec=st["color"], label=n)
        if xb:
            ax.scatter(xb, yb, marker=st["marker"], facecolors="none", edgecolors=st["color"],
                       lw=0.5, s=9, label=None if xa else n)
    if E["eps_star"] is not None:
        ax.axvspan(eps_grid[0] * 0.9, E["eps_star"], color="0.92", lw=0, zorder=0)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(eps_grid)
    shown = {0.02, 0.05, 0.1, 0.2, 0.5}
    ax.set_xticklabels([f"{e:g}" if e in shown else "" for e in eps_grid])
    ax.minorticks_off()
    ax.set_xlim(eps_grid[0] * 0.9, eps_grid[-1] * 1.1)
    ax.set_xlabel(r"dilution rate $\varepsilon$")
    ax.set_ylabel("USD (log)")
    ax.scatter([], [], marker="o", facecolors="none", edgecolors="0.4", lw=0.5, s=9,
               label="hollow: too many false alarms")
    fig.legend(loc="outside lower center", ncol=2, handlelength=1.8, columnspacing=1.2,
               fontsize=7)
    save(fig, "fig_break_even", plt)


def fig_coverage(plt, rows):
    rows = sorted(rows, key=lambda r: r[1] / r[2])
    fig, ax = plt.subplots(figsize=(W, 0.22 * len(rows) + 0.45))
    y = np.arange(len(rows))
    ax.barh(y, [k / n for _, k, n in rows], height=0.6, color="0.45")
    for yi, (_, k, n) in zip(y, rows):
        ax.text(k / n + 0.015, yi, f"{k}/{n}", va="center", fontsize=7.5)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlim(0, 1.15)
    ax.set_xticks([0, 0.5, 1.0])
    ax.set_xticklabels(["0%", "50%", "100%"])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("endpoints where the auditor can run")
    save(fig, "fig_coverage", plt)


def fig_evasion(plt, ev, lad="mock"):
    hold = ev.sel(lad, "holdout")
    names = AUD[:5] + ["RUT", "FUSE"]
    arms = ARMS[1:]
    mat = []
    for n in names:
        line = []
        for arm in arms:
            if n == "RUT":
                line.append(None)
                continue
            line.append(auroc(Evidence.scores(ev.sel(lad, "grid", arm), n), Evidence.scores(hold, n)))
        mat.append(line)
    fig, ax = plt.subplots(figsize=(W, 1.95))
    ax.grid(False)
    for i, line in enumerate(mat):
        for j, v in enumerate(line):
            if v is None:
                ax.add_patch(plt.Rectangle((j - .5, i - .5), 1, 1, facecolor="white",
                                           edgecolor="0.85", lw=0.4, hatch="////"))
                continue
            t = max(0.0, min(1.0, (v - 0.5) / 0.5))
            ax.add_patch(plt.Rectangle((j - .47, i - .47), .94, .94, facecolor=str(1 - 0.8 * t),
                                       edgecolor="none"))
            ax.text(j, i, f"{v:.2f}".lstrip("0") if round(v, 2) < 1 else "1", ha="center", va="center",
                    fontsize=7, color="white" if t > 0.55 else "black")
    ax.set_xlim(-.5, len(arms) - .5)
    ax.set_ylim(len(names) - .5, -.5)
    ax.set_xticks(range(len(arms)))
    # * honest arm; ? ambiguous ground truth (A2 uses the same honest provider as A11).
    ax.set_xticklabels([a + ("*" if not IS_SUB[a] else "?" if a == "A2" else "") for a in arms])
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    save(fig, "fig_evasion", plt)
    return mat


def fig_fpr(plt, ev, v1):
    names = AUD
    series = [
        ("v1 holdout, as run ($\\geq$)", [(v1["holdout"][n]["ge"], v1["holdout"][n]["n"]) for n in names], "o", "0.6", "0.6"),
        ("v1 fresh blocks ($>$)", [v1["fresh"].get(n, (0, 0)) for n in names], "s", "0.6", "white"),
        ("v2 holdout, hand-written", [Evidence.rate(ev.sel("mock", "holdout"), n) for n in names], "D", "0.0", "0.0"),
        ("v2 holdout, fitted", [Evidence.rate(ev.sel("mock-fit", "holdout"), n) for n in names], "^", "0.0", "white"),
    ]
    fig, ax = plt.subplots(figsize=(W, 2.1))
    for j, (label, ks, mk, col, mfc) in enumerate(series):
        keep = [i for i, (_, m) in enumerate(ks) if m > 0]      # FUSE was not in v1's fresh blocks
        ks = [ks[i] for i in keep]
        y = np.array(keep) + (j - 1.5) * 0.17
        p, err = wilson_err(ks)
        ax.errorbar(p, y, xerr=err, fmt=mk, color=col, mfc=mfc, mec=col, ms=3.2,
                    elinewidth=0.5, capsize=0, label=label)
    ax.axvline(ev.alpha, color="0.0", lw=0.6, ls="--")
    ax.text(ev.alpha, -0.85, r" $\alpha$ = 1%", fontsize=7.5, va="bottom")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.set_ylim(len(names) - 0.5, -0.9)
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(plt.matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("realised false-positive rate (Wilson 95%)")
    ax.legend(loc="lower right", fontsize=7, handletextpad=0.3)
    save(fig, "fig_fpr", plt)


def fig_confound(plt, ev, lad="mock"):
    a3 = ev.sel(lad, "eps", "A3", 0.10)
    a11 = ev.sel(lad, "eps", "A11", None)
    fig, ax = plt.subplots(figsize=(W, 1.75))
    x = np.arange(len(AUD))
    for off, rows, mk, mfc, label in [(-0.12, a3, "o", "0.0", r"A3 fraud, $\varepsilon$=0.10"),
                                       (0.12, a11, "s", "white", "A11 benign routing")]:
        ks = [Evidence.rate(rows, n) for n in AUD]
        p, err = wilson_err(ks)
        ax.errorbar(x + off, p, yerr=err, fmt=mk, color="0.0", mfc=mfc, ms=3.4,
                    elinewidth=0.5, capsize=0, label=label)
    for i, n in enumerate(AUD):
        v = auroc(Evidence.scores(a3, n), Evidence.scores(a11, n))
        ax.text(i, 1.08, f"{v:.2f}", ha="center", fontsize=7.5)
    ax.text(-0.7, 1.08, "AUROC", ha="right", fontsize=7.5)
    ax.set_xticks(x)
    ax.set_xticklabels(AUD)
    ax.set_ylim(-0.03, 1.15)
    ax.set_ylabel("sessions flagged")
    ax.yaxis.set_major_formatter(plt.matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.grid(axis="x", visible=False)
    ax.legend(loc="center left", bbox_to_anchor=(0.0, 0.6), fontsize=7.5)
    save(fig, "fig_confound", plt)


def fig_live(plt):
    obs = load_jsonl(RES / "live" / "observations.jsonl")
    fig, ax = plt.subplots(figsize=(W, 1.9))
    styles = {"REF": ("0.0", "-"), "A0": ("0.55", "-"), "A1": ("0.0", "--"),
              "A3": ("0.45", "-."), "A9": ("0.0", ":")}
    names = {"REF": "REF (120b, honest)", "A0": "A0 honest", "A1": "A1 (20b)",
             "A3": r"A3 $\varepsilon$=0.10", "A9": "A9 latency shaping"}
    for lab, (c, ls) in styles.items():
        x = np.sort([r["client_latency_s"] for r in obs if r["label"] == lab and r["ok"]])
        ax.step(x, np.arange(1, len(x) + 1) / len(x), where="post", color=c, ls=ls, lw=0.9,
                label=names[lab])
    ax.set_xscale("log")
    ax.set_xlim(0.2, 5)
    ax.set_xticks([0.2, 0.5, 1, 2, 5])
    ax.set_xticklabels(["0.2", "0.5", "1", "2", "5"])
    ax.minorticks_off()
    ax.set_xlabel("client-side latency (s, log)")
    ax.set_ylabel("ECDF")
    ax.legend(loc="lower right", fontsize=7)
    save(fig, "fig_live", plt)


# ---------------------------------------------------------------- tables
def md_table(head, rows) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + \
           ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def write_tables(ev, eco, auc_mats) -> None:
    TAB.mkdir(parents=True, exist_ok=True)
    sha = ev.p["sha256"]
    hdr = [f"Protocol v2 `{sha[:16]}...` (tag `frozen-v2`). Decision: score > sealed max of "
           f"{ev.p['calibration']['n']} honest sessions; FUSE at e >= {1 / ev.alpha:g}. "
           f"Intervals are Wilson 95%.\n"]

    L = ["# v2 holdout: realised false-positive rate\n"] + hdr
    rows = []
    for n in AUD:
        rows.append([n] + [f"{Evidence.rate(ev.sel(l, 'holdout'), n)[0]}/"
                           f"{Evidence.rate(ev.sel(l, 'holdout'), n)[1]} = "
                           f"{pct_ci(*Evidence.rate(ev.sel(l, 'holdout'), n))}" for l in eco]
                    + [f"{ev.p['thresholds'][l][n]['threshold']:+.4f}" for l in eco])
    L += md_table(["Auditor"] + [f"FPR, {LADDER_NAME[l]}" for l in eco]
                  + [f"threshold, {l}" for l in eco], rows)
    (TAB / "holdout.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    for l in eco:
        n_seeds = len(ev.sel(l, "grid", "A0"))
        G = [f"# v2 grid, {LADDER_NAME[l]}: flag rate per arm ({n_seeds} sessions each)\n"] + hdr + [
            "Genuine arms (A0, A4, A11): any flag is a false positive. RUT is inapplicable "
            "everywhere (no logprobs) and is omitted.\n"]
        rows = []
        for arm in ARMS:
            rows.append([arm, "sub" if IS_SUB[arm] else "genuine"] +
                        [pct_ci(*Evidence.rate(ev.sel(l, "grid", arm), n), dec=0) for n in AUD])
        G += md_table(["Arm", "truth"] + AUD, rows)
        G += ["", f"## AUROC vs the {len(ev.sel(l, 'holdout'))}-session holdout", ""]
        rows = [[arm] + [("-" if auc_mats[l][i][j] is None else f"{auc_mats[l][i][j]:.2f}")
                         for i in range(len(AUD[:5] + ['RUT', 'FUSE']))] for j, arm in enumerate(ARMS[1:])]
        G += md_table(["Arm"] + AUD[:5] + ["RUT", "FUSE"], rows)
        (TAB / f"grid_{l}.md").write_text("\n".join(G) + "\n", encoding="utf-8")

    P = ["# v2 dilution sweep: power per session\n"] + hdr
    for l, E in eco.items():
        P += ["", f"## {LADDER_NAME[l]}", ""]
        rows = [[f"{e:g}"] + [pct_ci(*E["power"][e][n], dec=0) for n in AUD] for e in E["power"]]
        rows.append(["A11 (genuine)"] + [pct_ci(*Evidence.rate(ev.sel(l, "eps", "A11", None), n), dec=0)
                                         for n in AUD])
        P += md_table(["eps"] + AUD, rows)
    (TAB / "eps_power.md").write_text("\n".join(P) + "\n", encoding="utf-8")

    A = ev.p["analysis"]
    C = ["# v2 economics and eps*\n"] + hdr + [
        f"Rules sealed in protocol v2: power target {A['power_target']:.0%}, family FPR budget "
        f"{A['family_fpr_budget']:.0%}, per-session FPR = holdout rate floored at "
        f"{ev.p['calibration']['marginal_fpr_bound']:.4f}, saving = ${A['monthly_spend_usd']:,.0f} x "
        f"eps x (1 - price ratio). Bootstrap: {A['eps_star_ci']['replicates']} replicates over "
        f"sessions.\n"]
    for l, E in eco.items():
        b = E["boot"]
        C += ["", f"## {LADDER_NAME[l]}", "",
              f"Price ratio substitute/genuine: **{E['price']['ratio']:.3f}**. "
              f"**eps\\* = {E['eps_star']}**, bootstrap 95% interval "
              f"[{b['lo']}, {b['hi'] if b['hi'] is not None else '> 0.5'}]. "
              f"Winner: {E['winner'][0] if E['winner'] else '-'}"
              + (f" ({E['winner'][1]} sessions, power/session {E['winner'][3]:.0%}, "
                 f"${E['winner'][2]:.4f})" if E["winner"] else "") + ".", "",
              "Bootstrap distribution of eps*: " + ", ".join(
                  f"{k}: {v:.1%}" for k, v in b["dist"].items() if v > 0) + "\n"]
        rows = [[n, f"{E['f'][n][1]}/{E['f'][n][2]}", f"{E['f'][n][0]:.2%}",
                 "unbounded" if math.isinf(E["kmax"][n]) else E["kmax"][n], f"{E['cost'][n]:.5f}"]
                for n in AUD]
        C += md_table(["Auditor", "holdout flags", "f used", "max admissible sessions",
                       "cost/session USD"], rows)
    (TAB / "economics.md").write_text("\n".join(C) + "\n", encoding="utf-8")

    F = ["# v2 confound: A3 at eps = 0.10 vs A11 (benign routing)\n"] + hdr
    for l in eco:
        a3, a11 = ev.sel(l, "eps", "A3", 0.10), ev.sel(l, "eps", "A11", None)
        rows = [[n, pct_ci(*Evidence.rate(a3, n), dec=0), pct_ci(*Evidence.rate(a11, n), dec=0),
                 f"{auroc(Evidence.scores(a3, n), Evidence.scores(a11, n)):.2f}"] for n in AUD]
        F += ["", f"## {LADDER_NAME[l]} ({len(a3)} sessions each)", ""]
        F += md_table(["Auditor", "flags A3", "flags A11", "AUROC A3 vs A11"], rows)
    (TAB / "confound.md").write_text("\n".join(F) + "\n", encoding="utf-8")
    print("  wrote results/v2/tables/{holdout,grid_*,eps_power,economics,confound}.md")


# ---------------------------------------------------------------- numbers sheet
def write_numbers(ev, eco, v1, census, cov, auc_mats, posthoc) -> None:
    fit = yaml.safe_load((ROOT / "config" / "mock_fit.yaml").read_text(encoding="utf-8"))
    live = json.loads((RES / "live" / "summary.json").read_text(encoding="utf-8"))
    p = ev.p
    L = ["# Paper numbers\n",
         "Every number the paper cites, with the file it comes from. Generated by "
         "`scripts/15_paper.py`; do not edit by hand. Rates carry Wilson 95% intervals "
         "`p [lo, hi]`.\n",
         f"- Protocol v1: `{v1['sha']}` (tag `frozen-v1`), reported as sealed.",
         f"- Protocol v2: `{p['sha256']}` (tag `frozen-v2`); fitted-mock parameters sealed by "
         f"hash `{list(p['sealed_inputs'].values())[0][:16]}...`.", ""]

    L += ["## 1. Coverage on the free-tier fleet  (results/tables/coverage.md)", ""]
    L += md_table(["Auditor", "endpoints"], [[n, f"{k}/{m}"] for n, k, m in cov])

    L += ["", "## 2. Protocol and calibration  (config/protocol_v2.yaml)", ""]
    c = p["calibration"]
    L += md_table(["Quantity", "Value"], [
        ["alpha", p["alpha"]],
        ["v1 calibration sessions / marginal bound", "100 / 0.99%"],
        ["v2 calibration sessions", c["n"]],
        ["v2 marginal FPR bound 1/(N+1)", f"{c['marginal_fpr_bound']:.2%}"],
        ["v2 training-conditional: P(realised FPR > alpha) <=", f"{c['training_conditional']['delta']:.1%}"],
        ["v2 decision rule", "score > threshold (v1: >=)"],
        ["queries per session", p["conditions"]["queries_per_session"]],
        ["v2 seeds: holdout / per arm / per eps",
         f"{p['seeds']['holdout'][1] - p['seeds']['holdout'][0] + 1} / "
         f"{p['seeds']['grid_arms'][1] - p['seeds']['grid_arms'][0] + 1} / "
         f"{p['seeds']['eps_sweep'][1] - p['seeds']['eps_sweep'][0] + 1}"],
    ])

    L += ["", "## 3. Realised false-positive rates  (results/v2/tables/holdout.md, results/grid.jsonl, "
          "results/threshold_audit.json)", ""]
    rows = []
    for n in AUD:
        h = v1["holdout"][n]
        fr = v1["fresh"].get(n)
        rows.append([n,
                     f"{v1['thr'][n]:+.4f}" if n != "FUSE" else "e>=100",
                     pct_ci(h["ge"], h["n"]), pct_ci(h["gt"], h["n"]),
                     pct_ci(*fr) if fr else "-",
                     f"{p['thresholds']['mock'][n]['threshold']:+.4f}" if n != "FUSE" else "e>=100",
                     pct_ci(*Evidence.rate(ev.sel("mock", "holdout"), n)),
                     pct_ci(*Evidence.rate(ev.sel("mock-fit", "holdout"), n))])
    L += md_table(["Auditor", "v1 thr", "v1 holdout (>=, as run)", "v1 holdout (>)",
                   "v1 fresh blocks B+C (>)", "v2 thr (hand)", "v2 holdout hand", "v2 holdout fitted"],
                  rows)
    L += ["", "v1 diagnosis re-measured for v2: GATEOPS exceeds its v1 threshold on ~5% of fresh "
          "honest sessions in every block (400 + 300 sessions); the sealed block's 0/100 is a "
          "~1-in-300 draw. The v1 report's 'discreteness' explanation is superseded: the marginal "
          "conformal bound holds for discrete statistics; a single unlucky calibration draw does not."]

    for l in eco:
        E = eco[l]
        b = E["boot"]
        L += ["", f"## 4{'ab'[list(eco).index(l)]}. Economics, {LADDER_NAME[l]}  "
              f"(results/v2/tables/economics.md)", ""]
        w = E["winner"]
        L += md_table(["Quantity", "Value"], [
            ["price ratio substitute/genuine", f"{E['price']['ratio']:.3f}"],
            ["eps*", E["eps_star"]],
            ["eps* bootstrap 95% interval", f"[{b['lo']}, {b['hi'] if b['hi'] is not None else '> 0.5'}]"],
            ["eps* bootstrap distribution", ", ".join(f"{k}: {v:.1%}" for k, v in b["dist"].items() if v > 0)],
            ["winning auditor at eps*", w[0] if w else "-"],
            ["its power per session at eps*", pct_ci(*E["power"][E["eps_star"]][w[0]], dec=0) if w else "-"],
            ["sessions to 80% / admissible max", f"{w[1]} / {E['kmax'][w[0]]}" if w else "-"],
            ["audit cost to 80% at eps* (USD)", f"{w[2]:.4f}" if w else "-"],
            ["adversary saving at eps*, $1,000/month", f"{E['save'][E['eps_star']]:.2f}" if w else "-"],
            ["adversary saving at eps=0.05", f"{E['save'][0.05]:.2f}"],
        ])
        L += ["", "Power per session (A3):", ""]
        L += md_table(["eps"] + AUD, [[f"{e:g}"] + [pct_ci(*E["power"][e][n], dec=0) for n in AUD]
                                      for e in E["power"]])

    for l in eco:
        a3, a11 = ev.sel(l, "eps", "A3", 0.10), ev.sel(l, "eps", "A11", None)
        L += ["", f"## 5{'ab'[list(eco).index(l)]}. Confound A3@0.10 vs A11, {LADDER_NAME[l]}  "
              f"(results/v2/tables/confound.md)", ""]
        L += md_table(["Auditor", "flags A3", "flags A11", "AUROC A3 vs A11"],
                      [[n, pct_ci(*Evidence.rate(a3, n), dec=0), pct_ci(*Evidence.rate(a11, n), dec=0),
                        f"{auroc(Evidence.scores(a3, n), Evidence.scores(a11, n)):.2f}"] for n in AUD])

    for l in eco:
        L += ["", f"## 6{'ab'[list(eco).index(l)]}. Grid AUROC vs holdout, {LADDER_NAME[l]}  "
              f"(results/v2/tables/grid_{l}.md)", ""]
        names = AUD[:5] + ["RUT", "FUSE"]
        L += md_table(["Arm"] + names, [[arm] + ["-" if auc_mats[l][i][j] is None else f"{auc_mats[l][i][j]:.2f}"
                                                 for i in range(len(names))] for j, arm in enumerate(ARMS[1:])])
        L += ["", "Max AUROC on A5 across auditors: "
              f"{max(v for v in (auc_mats[l][i][ARMS[1:].index('A5')] for i in range(len(names))) if v is not None):.2f}"]

    L += ["", "## 7. Fitted mock  (config/mock_fit.yaml)", ""]
    rows = []
    for name, m in fit["models"].items():
        lat = m["latency"]
        rows.append([name, m["source"], f"{lat['mean_s']:.3f}", f"{lat['cv']:.2f}",
                     f"{lat.get('ks_fit_p', float('nan')):.2f}" if "ks_fit_p" in lat else "-"])
    L += md_table(["mock model", "source", "latency mean s", "CV", "KDE fit KS p"], rows)
    L += ["", "Hand-written latency means: genuine 1.10 s, substitute 0.35 s (ratio 3.1x); "
          "fitted: see above. Lognormal rejected for real latency (KS p < 0.001)."]

    L += ["", "## 8. Real recorded responses, OTE on the census  (corpus/, recomputed)", ""]
    ot, fps, nrec = census
    L += md_table(["Comparison", "OTE divergence", "OTE Fisher p", "cells",
                   "IRIS-lite CV accuracy", "IRIS-lite p"],
                  [[r["case"], f"{r['score']:+.4f}", f"{r['fisher_p']:.2g}", r["n_cells"],
                    f"{r['iris_cv_accuracy']:.2f}", f"{r['iris_p']:.2g}"] for r in ot])
    L += ["", "IRIS-lite on the census reads only the 8 OTE cells (short numeric and coin "
          "answers), not its own suite, so it is a check of its surface features on real text, "
          "not a full run."]
    L += ["", f"Distinct system_fingerprint values: 120b {fps['120b']} in {nrec['120b']} honest requests; "
          f"20b {fps['20b']} in {nrec['20b']}."]

    L += ["", "## 9. POST-HOC sensitivity: eps* without IRIS-lite  (NOT in the v2 seal)", "",
          "Motivation, found after the v2 evaluation: on both ladders eps* is set by IRIS-lite, "
          "whose signal is the mock's hand-written surface habits (not fitted), and on real census "
          "text IRIS-lite does not separate gpt-oss-20b from 120b (section 8). Same sealed rule "
          "and bootstrap, IRIS-lite removed from the candidate auditors. Report as exploratory.", ""]
    rows = []
    for l, E in posthoc.items():
        b, w = E["boot"], E["winner"]
        rows.append([LADDER_NAME[l], E["eps_star"],
                     f"[{b['lo']}, {b['hi'] if b['hi'] is not None else '> 0.5'}]",
                     ", ".join(f"{k}: {v:.1%}" for k, v in b["dist"].items() if v > 0),
                     w[0] if w else "-",
                     pct_ci(*E["power"][E["eps_star"]][w[0]], dec=0) if w else "-",
                     f"{w[1]} / {E['kmax'][w[0]]}" if w else "-"])
    L += md_table(["ladder", "eps*", "bootstrap 95%", "bootstrap distribution", "winner",
                   "power/session at eps*", "sessions / admissible"], rows)

    L += ["", "## 10. Live run on Groq  (results/live/summary.json)", ""]
    rows = []
    for lab, s in live["labels"].items():
        g, o = s.get("gateops", {}), s.get("ote", {})
        rows.append([lab, s["arm"], f"{s['truth']['substituted']}/{s['truth']['ledger_rows']}",
                     f"{s['median_latency_s']:.3f}", f"{s['p90_latency_s']:.3f}", f"{s['cv']:.2f}",
                     f"{g['ks']:.2f} (p={g['ks_p']:.2g})" if g else "reference",
                     f"{o['fisher_p']:.2g}" if o else "-",
                     len(g.get("fingerprint_novel", [])) if g else "-"])
    L += md_table(["Label", "arm", "swapped", "median s", "p90 s", "CV", "KS vs REF",
                   "OTE Fisher p", "novel fp"], rows)
    ref, a1 = live["labels"]["REF"], live["labels"]["A1"]
    L += ["", f"Real speed gap 20b vs 120b (medians): "
          f"{1 - a1['median_latency_s'] / ref['median_latency_s']:.0%} faster; "
          f"REF distinct fingerprints: {len(live['reference_fingerprints'])} in 96."]
    NUMBERS.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  wrote {NUMBERS.relative_to(ROOT)}")


def main() -> int:
    protocol = load_sealed(ROOT / "config" / "protocol_v2.yaml")
    rows = [r for r in load_jsonl(V2 / "sessions.jsonl") if r["protocol_sha256"] == protocol["sha256"]]
    if not rows:
        raise SystemExit("no v2 sessions for this protocol - run scripts/14_evaluate_v2.py")
    ev = Evidence(protocol, rows)
    print(f"Paper evidence - protocol v2 {protocol['sha256'][:16]}..., {len(rows)} sessions")

    eco = {l: economics(ev, l) for l in protocol["conditions"]["ladders"]}
    for l, E in eco.items():
        print(f"  {l:<9} eps* = {E['eps_star']}  bootstrap [{E['boot']['lo']}, {E['boot']['hi']}]  "
              f"winner {E['winner'][0] if E['winner'] else '-'}")
    v1 = v1_evidence()
    census = census_ote()
    posthoc = {l: economics(ev, l, exclude=("IRIS-lite",)) for l in eco}
    for l, E in posthoc.items():
        print(f"  post-hoc, no IRIS-lite, {l:<9} eps* = {E['eps_star']}  "
              f"bootstrap [{E['boot']['lo']}, {E['boot']['hi']}]")
    cov = coverage_rows()

    plt = setup_mpl()
    auc = {l: fig_evasion(plt, ev, l) if l == "mock" else None for l in eco}
    for l in eco:
        if auc[l] is None:
            hold = ev.sel(l, "holdout")
            auc[l] = [[None if n == "RUT" else auroc(Evidence.scores(ev.sel(l, "grid", a), n),
                                                     Evidence.scores(hold, n)) for a in ARMS[1:]]
                      for n in AUD[:5] + ["RUT", "FUSE"]]
    fig_power(plt, ev, eco)
    fig_break_even(plt, ev, eco)
    fig_coverage(plt, cov)
    fig_fpr(plt, ev, v1)
    fig_confound(plt, ev)
    fig_live(plt)
    write_tables(ev, eco, auc)
    write_numbers(ev, eco, v1, census, cov, auc, posthoc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
