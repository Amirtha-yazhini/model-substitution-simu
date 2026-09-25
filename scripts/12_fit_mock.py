"""Protocol v2, step 1 - fit the mock to measurement.

The v1 grid runs on hand-written model "personalities". The obvious reviewer
question is whether its conclusions are properties of the auditors or of those
personalities. This script replaces the two measurable ones with data:

  answers   Per-cell answer distributions for Bruckner's 8 OTE cells, pooled from
            the census (30 per cell) and the Phase 6 live run (REF + A0 for the
            120b, A1 for the 20b; 12 per cell per label). Unseen mass follows
            Good-Turing (singletons / n), spread evenly over the unseen values,
            so a value never observed is rare rather than impossible.
  latency   Kernel density on log-latency (Silverman bandwidth), fitted to
            client-side wall time from the live run - the only latencies in this project measured the way an
            auditor measures them.

  genuine-70b    <- groq:openai/gpt-oss-120b
  substitute-8b  <- groq:openai/gpt-oss-20b
  alternate-70b  NOT MEASURABLE: no second free provider serves gpt-oss-120b (A11
                 was blocked live). Uses genuine's fitted answers (same weights)
                 and genuine's fitted latency scaled by the hand-written
                 alternate/genuine ratios.
  launderer      substitute's fitted answers; latency scaled by the hand-written
                 launderer/substitute ratios.

Everything else (surface habits, factual accuracy, token counts, non-OTE suites)
is copied unchanged from the hand-written model, so the two ladders differ only
in what was fitted. The output is sealed into protocol v2 by its SHA-256.

    python scripts/12_fit_mock.py            # print the fit, write nothing
    python scripts/12_fit_mock.py --write    # write config/mock_fit.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.auditors.ote import extract_answer  # noqa: E402
from arena.probes.ote_probes import probe_set  # noqa: E402
from shim.mock import MOCK_MODELS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
LIVE = ROOT / "results" / "live" / "observations.jsonl"
OUT = ROOT / "config" / "mock_fit.yaml"

SOURCES = {
    "genuine-70b": {"corpus": "groq__openai__gpt-oss-120b.jsonl", "live": ("REF", "A0"),
                    "endpoint": "groq:openai/gpt-oss-120b"},
    "substitute-8b": {"corpus": "groq__openai__gpt-oss-20b.jsonl", "live": ("A1",),
                      "endpoint": "groq:openai/gpt-oss-20b"},
}
# Unmeasurable models borrow a fitted anchor, scaled by the hand-written ratio.
DERIVED = {"alternate-70b": "genuine-70b", "launderer": "substitute-8b"}


def universe(cell: str) -> list[str]:
    if cell.startswith("rand100"):
        return [str(v) for v in range(1, 101)]
    if cell.startswith("coin"):
        return ["heads", "tails"]
    raise ValueError(cell)


def good_turing(answers: list[str | None], cell: str) -> dict[str, float]:
    """Empirical distribution with Good-Turing mass for unseen values.

    Unparsable replies are kept as "" at their observed rate: on the real fleet
    they happen, and OTE has to cope with them.
    """
    n = len(answers)
    c = Counter("" if a is None else a for a in answers)
    n1 = sum(1 for v in c.values() if v == 1)
    unseen = [u for u in universe(cell) if u not in c]
    p0 = (n1 / n) if unseen else 0.0
    dist = {k: (1 - p0) * v / n for k, v in c.most_common()}
    for u in unseen:
        dist[u] = p0 / len(unseen)
    return dist


def fit_latency(xs: list[float], seed: int = 0) -> dict:
    """Kernel density on log-latency, Silverman bandwidth.

    A lognormal was the first choice and the data rejected it (KS p < 0.001):
    real Groq latency has a tight core around 0.6-0.7 s and a separate slow tail
    out to 4.5 s, which one lognormal cannot hold at both ends. Resampling the
    measured times with a small log-scale jitter keeps both, and the fit is
    checked the same way - a two-sample KS between data and draws.
    """
    import random

    from scipy.stats import ks_2samp

    logs = sorted(math.log(x) for x in xs)
    n = len(logs)
    sd = statistics.stdev(logs)
    iqr = logs[int(0.75 * n)] - logs[int(0.25 * n)]
    h = 0.9 * min(sd, iqr / 1.34) * n ** -0.2
    rng = random.Random(seed)
    draws = [math.exp(rng.choice(logs) + rng.gauss(0, h)) for _ in range(20000)]
    ks = ks_2samp(xs, draws)
    mean = statistics.fmean(draws)
    return {
        "model": "kde_log",
        "log_samples": [round(v, 6) for v in logs],
        "bandwidth_log": h,
        "mean_s": mean,
        "cv": statistics.pstdev(draws) / mean,
        "median_s": statistics.median(xs),
        "n": n,
        "ks_fit_stat": float(ks.statistic), "ks_fit_p": float(ks.pvalue),
    }


def derived_latency(anchor: dict, mean_ratio: float, spread_ratio: float) -> dict:
    """The anchor's fitted KDE, shifted by a mean ratio and stretched about its
    log-median by a spread ratio - both taken from the hand-written models."""
    logs = anchor["log_samples"]
    med = statistics.median(logs)
    shifted = sorted(med + math.log(mean_ratio) + spread_ratio * (v - med) for v in logs)
    return {
        "model": "kde_log",
        "log_samples": [round(v, 6) for v in shifted],
        "bandwidth_log": anchor["bandwidth_log"] * spread_ratio,
        "mean_s": anchor["mean_s"] * mean_ratio,
        "cv": anchor["cv"] * spread_ratio,
        "rule": f"anchor's fitted KDE x mean ratio {mean_ratio:.3f}, "
                f"log-spread x {spread_ratio:.3f} (hand-written ratios)",
    }


def entropy_bits(dist: dict[str, float]) -> float:
    return -sum(p * math.log2(p) for p in dist.values() if p > 0)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fit the mock ladder to census + live data.")
    ap.add_argument("--write", action="store_true", help="write config/mock_fit.yaml")
    args = ap.parse_args()

    live = [json.loads(l) for l in LIVE.read_text(encoding="utf-8").splitlines() if l.strip()]
    prompts = {p.cell: p.prompt for p in probe_set("core")}
    models: dict[str, dict] = {}

    for name, src in SOURCES.items():
        census = [json.loads(l) for l in (CORPUS / src["corpus"]).read_text(
            encoding="utf-8").splitlines() if l.strip()]
        cells = {}
        for cell, prompt in prompts.items():
            a_c = [extract_answer(r["body"]["choices"][0]["message"].get("content") or "", cell)
                   for r in census if r["ok"] and r["cell"] == cell]
            a_l = [extract_answer(r.get("text") or "", cell)
                   for r in live if r["ok"] and r["label"] in src["live"] and r["cell"] == cell]
            dist = good_turing(a_c + a_l, cell)
            cells[cell] = {
                "prompt": prompt, "n_census": len(a_c), "n_live": len(a_l),
                "entropy_bits": round(entropy_bits(dist), 4),
                "dist": {k: round(v, 6) for k, v in dist.items()},
            }
        lat = [r["client_latency_s"] for r in live
               if r["ok"] and r["label"] in src["live"] and r.get("client_latency_s")]
        models[name] = {"source": src["endpoint"], "fitted": ["answers.ote_cells", "latency"],
                        "latency": fit_latency(lat), "cells": cells}

    for name, anchor in DERIVED.items():
        hand, hand_anchor = MOCK_MODELS[name], MOCK_MODELS[anchor]
        fitted = models[anchor]["latency"]
        models[name] = {
            "source": f"derived from {anchor} (not measurable on the free fleet)",
            "fitted": ["answers.ote_cells (anchor's)"],
            "latency": derived_latency(fitted, hand.latency_mean_s / hand_anchor.latency_mean_s,
                                       hand.latency_cv / hand_anchor.latency_cv),
            "cells": models[anchor]["cells"],
        }

    print("=" * 84)
    print("Mock fit - hand-written vs measured")
    print("=" * 84)
    print(f"{'model':<15} {'hand mean':>9} {'hand cv':>8} {'fit mean':>9} {'fit cv':>7}  "
          f"{'fit n':>5}  KDE-fit KS p")
    for name, m in models.items():
        h, L = MOCK_MODELS[name], m["latency"]
        print(f"{name:<15} {h.latency_mean_s:>9.3f} {h.latency_cv:>8.2f} {L['mean_s']:>9.3f} "
              f"{L['cv']:>7.2f}  {L.get('n', '-'):>5}  {L.get('ks_fit_p', float('nan')):.3f}")
    print("\nTop answers per cell (fitted):")
    for name in SOURCES:
        for cell, c in models[name]["cells"].items():
            top = sorted(c["dist"].items(), key=lambda kv: -kv[1])[:4]
            print(f"  {name:<14} {cell:<11} n={c['n_census'] + c['n_live']:<3} "
                  f"H={c['entropy_bits']:.2f}b  " + "  ".join(f"{k or '<none>'}:{v:.2f}" for k, v in top))

    doc = {
        "fit_version": 1,
        "inputs": {
            "corpus": {n: s["corpus"] for n, s in SOURCES.items()},
            "live": str(LIVE.relative_to(ROOT)).replace("\\", "/"),
            "input_sha256": {
                p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                for p in [f"corpus/{s['corpus']}" for s in SOURCES.values()]
                + ["results/live/observations.jsonl"]
            },
        },
        "method": {
            "answers": "pooled census + live, Good-Turing unseen mass spread evenly; "
                       "'' = unparsable reply at its observed rate",
            "latency": "KDE on log live client-side wall time, Silverman bandwidth (lognormal rejected, KS p<0.001)",
            "not_fitted": "surface habits, factual accuracy, tokens_per_char, and "
                          "non-OTE suites: copied from the hand-written model",
        },
        "models": models,
    }
    if not args.write:
        print("\nDry run. Re-run with --write to write config/mock_fit.yaml.")
        return 0
    OUT.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT)}  sha256 "
          f"{hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
