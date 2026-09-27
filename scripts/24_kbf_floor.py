"""Where is KBF's pooled floor when the simulator is not the limit?

EXPLORATORY, NOT SEALED; added after the fourth skeptical review
(paper/REVIEW_skeptical_4.md, M2). In 22_pooled_all_arms.py, KBF is the only
pooled auditor that stays quiet on honest traffic (A4, A11) and catches A10, and
it reaches eps = 0.07 at k = 64. But k was capped at 128 because only 200
simulated sessions exist per cheating rate. Here more sessions are simulated.

KBF reads only its own suite (15 items x 5 repeats), and every random draw in
the mock and in SHIM's routing is keyed on the prompt, the request body and the
session seed, so a KBF-only session reproduces the KBF score of a full session
exactly, once the gateway's request counter (and A11's routing counter) start
where the preceding OTE and IRIS suites would have left them. That is checked first on committed sessions, then:

  * 1,000 fresh sessions each of A0 (honest), A11 (honest load balancing) and A3
    at eps = 0.02, 0.03, 0.05, 0.07, on both simulated pairs, on seeds 70000+
    that no earlier run used;
  * the pooled test of 19_pooled_sessions.py (one-sided Welch t-test of k suspect
    sessions against M honest calibration sessions at 5%), for k up to 1,000 and
    two calibration sizes, M = 300 (as before) and M = 1,000;
  * its false-alarm rate on random splits of the 1,800 honest sessions, and its
    flag rate on A11.

    python scripts/24_kbf_floor.py

Output: results/v2/tables/kbf_floor.md
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arena.protocol import load_sealed  # noqa: E402

_spec = importlib.util.spec_from_file_location("paper15", ROOT / "scripts" / "15_paper.py")
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

OUT = P.TAB / "kbf_floor.md"
LEDGER = ROOT / "results" / "v2" / "_ledger" / "ledger_kbf_floor.jsonl"
N_NEW = 1000
SEED0 = 70000
EPS = [0.02, 0.03, 0.05, 0.07]
KS = [64, 128, 256, 512, 1000]
MS = [300, 1000]
BUDGET, TARGET, REPS = 0.05, 0.80, 1000

_W: dict = {}


def _init():
    from arena.auditors.kbf import KBFAuditor
    from shim.policy import load_arm_config
    _W.update(kbf=KBFAuditor(), cfg=load_arm_config(), refs={})


async def _kbf_obs(arm, seed, cfg, models):
    from arena.collect import collect
    from arena.probes.suites import suite
    from arena.runner import SUITE_PLAN, make_gateway
    gw = make_gateway(arm, seed, LEDGER, cfg, models)
    # A full session sends the OTE and IRIS suites first. The gateway's request
    # counter (a backend RNG input) and A11's routing counter must start where
    # they would have, or the KBF draws differ from a full session's.
    offset = 0
    for name, (probes, reps) in SUITE_PLAN.items():
        if name == "kbf":
            break
        offset += len(probes) * reps
    gw._nonce = offset
    if hasattr(gw.policy, "_n"):
        gw.policy._n = offset
    return await collect(gw, suite("kbf"), repeats=SUITE_PLAN["kbf"][1])


def job(j):
    from arena.runner import mock_models
    ladder, arm, eps, seed = j
    models = mock_models(ladder)
    if ladder not in _W["refs"]:
        _W["refs"][ladder] = asyncio.run(_kbf_obs("A0", 1, _W["cfg"], models))
    cfg = _W["cfg"] if eps is None else {**_W["cfg"], "A3": {**_W["cfg"]["A3"], "eps": eps}}
    res = _W["kbf"].audit(asyncio.run(_kbf_obs(arm, seed, cfg, models)), _W["refs"][ladder], cost_usd=0.0)
    return ladder, arm, eps, seed, (None if res.score != res.score else res.score)


def welch(x, c) -> bool:
    from scipy.stats import ttest_ind
    return bool(ttest_ind(x, c, equal_var=False, alternative="greater").pvalue < BUDGET)


def main() -> int:
    protocol = load_sealed(ROOT / "config" / "protocol_v2.yaml")
    rows = [r for r in P.load_jsonl(P.V2 / "sessions.jsonl") if r["protocol_sha256"] == protocol["sha256"]]
    cal_rows = [json.loads(l) for l in (P.V2 / "calibration.jsonl").read_text().splitlines() if l.strip()]
    ladders = protocol["conditions"]["ladders"]
    committed = [r for r in rows if r["split"] == "eps" and r["arm"] == "A3" and r["eps"] == 0.10][:10] + \
                [r for r in rows if r["split"] == "eps" and r["arm"] == "A11"][:10] + \
                [r for r in rows if r["split"] == "holdout"][:10]
    check_jobs = [(r["ladder"], r["arm"], r["eps"], r["seed"]) for r in committed]
    jobs = [(lad, "A0", None, SEED0 + i) for lad in ladders for i in range(N_NEW)]
    jobs += [(lad, "A11", None, SEED0 + N_NEW + i) for lad in ladders for i in range(N_NEW)]
    jobs += [(lad, "A3", e, SEED0 + (2 + j) * N_NEW + i) for lad in ladders
             for j, e in enumerate(EPS) for i in range(N_NEW)]
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 2, initializer=_init) as ex:
        check = list(ex.map(job, check_jobs, chunksize=4))
        out = list(ex.map(job, jobs, chunksize=16))
    same = sum(abs((c[4] or 0) - (r["auditors"]["KBF"]["score"] or 0)) < 1e-12 for c, r in zip(check, committed))
    print(f"reproduction: {same}/{len(committed)} committed KBF scores reproduced")

    rng = np.random.default_rng(0)
    L = ["# KBF's pooled floor with more simulated sessions (exploratory, NOT sealed)", "",
         f"Generated by `scripts/24_kbf_floor.py`. Reproduction check: {same}/{len(committed)} committed KBF "
         f"session scores reproduced exactly by KBF-only sessions. {N_NEW} fresh sessions per arm and "
         f"cheating rate on seeds {SEED0}+. Pooled test: one-sided Welch t-test of k suspect sessions vs M "
         f"honest calibration sessions at {BUDGET:.0%}; {REPS} random audits per cell.", ""]
    for lad in ladders:
        old = [s for r in cal_rows if r["ladder"] == lad and (s := r["auditors"]["KBF"]["score"]) is not None]
        old += [s for r in rows if r["ladder"] == lad and r["split"] == "holdout"
                and (s := r["auditors"]["KBF"]["score"]) is not None]
        new = lambda arm, eps=None: np.array([o[4] for o in out if o[0] == lad and o[1] == arm and o[2] == eps
                                              and o[4] is not None], float)
        honest = np.concatenate([np.array(old, float), new("A0")])
        a11 = new("A11")
        L += [f"## {P.LADDER_NAME[lad]}", "", f"Honest pool: {len(honest)} sessions.", "",
              "| M (calibration) | quantity | " + " | ".join(f"k={k}" for k in KS) + " |",
              "|---|---|" + "---|" * len(KS)]
        for m in MS:
            def rate(pool, k, fa=False):
                hits = 0
                for _ in range(REPS):
                    perm = rng.permutation(len(honest))
                    c = honest[perm[:m]]
                    x = honest[perm[m:m + k]] if fa else pool[rng.choice(len(pool), k, replace=False)]
                    hits += welch(x, c)
                return hits / REPS
            ok = [k for k in KS if m + k <= len(honest)]
            fa = {k: rate(None, k, fa=True) for k in ok}
            L.append(f"| {m} | false alarms (honest) | " + " | ".join(
                f"{fa[k]:.1%}" if k in fa else "-" for k in KS) + " |")
            L.append(f"| {m} | flags A11 (honest routing) | " + " | ".join(
                f"{rate(a11, k):.0%}" for k in KS) + " |")
            for e in EPS:
                L.append(f"| {m} | catches A3 eps={e} | " + " | ".join(f"{rate(new('A3', e), k):.0%}" for k in KS) + " |")
            print(lad, "M", m, "done")
        L.append("")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
