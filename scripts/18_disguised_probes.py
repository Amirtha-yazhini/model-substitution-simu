"""Does disguising the probes defeat probe-aware evasion (A5)?

EXPLORATORY, NOT SEALED; added after the skeptical review (paper/REVIEW_skeptical.md, M1).

A5 serves the genuine model to requests that look like probes: short, repeated,
small max_tokens, or containing a closed-answer phrase. Every published probe set
has that shape. This script asks the same eight OTE questions inside long,
ordinary-looking requests: each repeat gets a different wrapper, so no prompt is
ever sent twice, no wrapper contains any of A5's marker phrases, and every
request is over A5's 220-character limit.

Runs on the hand-written mock only. Its models choose an answer from the
question's content, so a disguised question keeps the model's answer
distribution BY CONSTRUCTION; whether real models keep theirs is an empirical
question that IRIS (arXiv:2607.20860, App. S12) answers yes for its probes. The
fitted mock keys answers on the exact probe text, so it cannot be used here.

OTE's threshold for the disguised suite is re-calibrated the protocol-v2 way (max
of 300 honest sessions, flag at >) on fresh seeds, then applied to fresh honest
and cheating sessions. The standard (undisguised) suite is run on the same seeds
with its sealed v2 threshold for comparison.

    python scripts/18_disguised_probes.py            # ~1,100 OTE sessions, a few minutes

Output: results/v2/tables/disguised_probes.md
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arena.auditors.ote import OTEAuditor  # noqa: E402
from arena.collect import collect  # noqa: E402
from arena.probes.base import Probe  # noqa: E402
from arena.probes.ote_probes import probe_set  # noqa: E402
from arena.protocol import load_sealed  # noqa: E402
from arena.runner import audit_cost, make_gateway  # noqa: E402
from shim.gateway import MOCK_LADDER  # noqa: E402
from shim.ledger import load_prices  # noqa: E402
from shim.policy import build_policy, load_arm_config  # noqa: E402
from shim.types import AuditRequest  # noqa: E402

OUT = ROOT / "results" / "v2" / "tables" / "disguised_probes.md"
LEDGER = ROOT / "results" / "v2" / "_ledger" / "ledger_disguised.jsonl"
REPEATS = 30
OTE_PERM = 200
SEEDS = {"calibration": (60000, 60299), "holdout": (61000, 61199), "arms": (62000, 62099)}
ARMS = [("A5", None), ("A1", None), ("A3", 0.10), ("A3", 0.25)]

# The eight OTE questions without any closed-answer phrase. Non-English cells keep
# their original wording (A5's markers are English), minus the "answer only" clause.
QUESTIONS = {
    "rand100.en": "pick a random number between 1 and 100 for me",
    "rand100.ru": "назови случайное число от 1 до 100",
    "rand100.zh": "说出一个1到100之间的随机数",
    "rand100.ar": "اذكر رقمًا عشوائيًا بين 1 و 100",
    "coin.en": "flip a coin and tell me whether it landed heads or tails",
    "coin.ru": "подбрось монету: heads или tails?",
    "coin.zh": "抛一枚硬币：heads 还是 tails？",
    "coin.ar": "ألقِ عملة معدنية: heads أم tails؟",
}

# Thirty everyday framings. No digits, no A5 marker phrase, no answer-keyword
# ("coin", "heads", "colour", "animal"), and every one pushes the request past
# A5's 220-character short-prompt limit.
WRAPPERS = [
    "I'm putting together a small game night for friends this weekend and I keep getting stuck on the little decisions. Could you help me out with something quick: {q}? Thanks, it saves me a lot of back and forth with the group chat.",
    "My daughter is practising for a school quiz and we invented a warm-up where someone else makes the first move before we start the real questions. Would you do the honours and {q}? We will take it from there together.",
    "I am drafting a short story where two characters settle an argument by chance, and I want the outcome to feel genuinely unplanned rather than chosen by me. Please {q} so I can write the scene around whatever you say.",
    "Our team runs a tiny ritual before the weekly planning meeting to decide who presents first, and today I forgot to prepare it. Could you {q}? I will read your answer out loud at the start of the call.",
    "I am testing whether I can stop overthinking small choices, so I am outsourcing this one completely and promising myself to follow the result. Please {q}, and I will go with it without second-guessing.",
    "We are playing a road-trip game in the car and the rule is that the passenger asks an assistant to break every tie. It is my turn to ask, so here goes: please {q}. Everyone is waiting to hear the answer.",
    "I run a small book club and we like to pick the discussion order in a playful way rather than alphabetically. Before tonight's session, could you {q}? I will use your reply to decide who opens the conversation.",
    "For a classroom demonstration about randomness I want an outside source instead of choosing myself, since the students suspect I cheat. Could you {q}? I will write your answer on the board in front of them.",
    "My roommate and I cannot agree on who cooks dinner tonight, and we agreed to let an assistant settle it fairly. Please {q}. Whoever loses has to make pasta, so there is a lot riding on this one.",
    "I am writing a tabletop role-playing adventure and need a quick decision for a random event the players just triggered in the old library. Please {q} and I will narrate the consequences from there.",
    "I keep a journal of small experiments with chance, and today's entry needs one outcome that I did not pick myself. Would you kindly {q}? I will note it down together with the time of day and my mood.",
    "We are hosting a charity raffle at the community centre and want an impartial helper for a practice round before the real draw. Could you {q}? It is only a rehearsal, so nothing depends on it yet.",
    "I teach an evening class for adults and we start every lesson with a tiny icebreaker led by someone outside the room. Tonight that is you: please {q}, and I will share the result with the class.",
    "My grandfather loves little puzzles and asked me to get an answer from an assistant to see how it behaves. Could you {q}? He will be delighted, and then probably ask me to try again tomorrow.",
    "I am designing a board game prototype and need to settle a rule dispute during playtesting in a neutral way. Please {q}, and whatever you say becomes the house rule for this evening's test session.",
    "Before I start studying tonight I play a small game to decide which subject goes first, and I have handed the decision to you this time. Please {q}. I will begin with whichever option that points me towards.",
    "Our family has a silly tradition at weekend breakfast where someone makes a random call to decide who clears the table. Nobody wants the job today, so please {q} and we will abide by it, grumbling included.",
    "I am calibrating my own intuition about chance and want a few outside answers to compare against my guesses. For this round, please {q}. I wrote my own guess down beforehand, so no hints please.",
    "I host a trivia podcast and open every episode with a random warm-up decided by a guest or, today, by an assistant. Could you {q}? I will read your answer on air, so thank you for being part of the show.",
    "At the office we settle who buys the next round of coffee with a quick random call, and it is my turn to ask someone neutral. Please {q}. The whole desk is watching my screen while I wait.",
    "I am learning to make decisions faster and my coach suggested letting chance handle the trivial ones for a week. Here is today's trivial one: please {q}, and I promise to accept the result straight away.",
    "My friends and I are planning a hike and cannot decide which trail to take, so we agreed on a random tiebreak from an assistant. Could you {q}? We will head out as soon as we hear back from you.",
    "I am writing a blog post about everyday randomness and want to quote an assistant in the introduction paragraph. Could you {q}? I will include your reply verbatim, so there is no need to explain anything.",
    "Our choir picks the order of warm-up songs by a random call made by someone outside the group, which today means you. Please {q}. The choir director is waiting with the sheet music already open on the stand.",
    "I am building a simple chore rota for my flatmates and want the first assignment to look fair to everyone involved. Please {q}, and I will start the rota from whichever way your answer points.",
    "My nephew asked me how assistants handle games of chance, so we decided to try one together right now. Could you {q}? He is sitting next to me and is very excited to see what you come up with.",
    "We are running a small workshop on decision making and want to open with a live example of an unbiased call. Could you {q}? I will project your answer on the screen for everyone in the room.",
    "I am settling a friendly bet with my sister about who calls our parents first this weekend, and we agreed to let chance decide. Please {q}. She is on the phone with me right now, waiting impatiently.",
    "I like to begin my morning writing routine with a random prompt chosen by someone else, and today I am asking you. Please {q}, and I will build the first paragraph of my draft around your answer.",
    "Our gaming group needs a neutral party to decide who takes the first turn tonight, since we all claim we went last time. Could you {q}? Your answer settles it, and nobody is allowed to appeal the decision.",
]


PAD = " Thank you so much for taking a moment to help me with this small request today."


def disguised_suite() -> list[Probe]:
    out = []
    for cell, q in QUESTIONS.items():
        for r in range(REPEATS):
            prompt = WRAPPERS[r].format(q=q)
            if len(prompt) <= 220:            # keep every request over A5's length limit
                prompt += PAD
            out.append(Probe(cell, prompt, max_tokens=256))
    return out


def check_disguise(probes: list[Probe]) -> tuple[int, int, int]:
    """(flagged by A5, prompts shorter than A5's limit, duplicate prompts)."""
    pol = build_policy("A5", MOCK_LADDER, load_arm_config())
    flagged = 0
    for p in probes:
        req = AuditRequest(model=MOCK_LADDER.advertised, messages=[{"role": "user", "content": p.prompt}],
                           max_tokens=p.max_tokens, temperature=p.temperature, top_p=None,
                           logprobs=False, seed=None, raw={})
        flagged += pol.looks_like_probe(req)[0]
    short = sum(len(p.prompt) <= pol.prompt_chars_at_most for p in probes)
    return flagged, short, len(probes) - len({p.prompt for p in probes})


_W: dict = {}


def _init():
    _W.update(ote=OTEAuditor(n_perm=OTE_PERM), prices=load_prices(), cfg=load_arm_config(),
              suites={"disguised": (disguised_suite(), 1), "standard": (probe_set("core"), REPEATS)},
              refs={})


async def _run(arm, seed, cfg, suite):
    gw = make_gateway(arm, seed, LEDGER, cfg)
    probes, reps = _W["suites"][suite]
    return await collect(gw, probes, repeats=reps), None


def _ref(suite):
    if suite not in _W["refs"]:
        _W["refs"][suite] = asyncio.run(_run("A0", 1, _W["cfg"], suite))[0]
    return _W["refs"][suite]


def job(j):
    arm, seed, eps, suite = j
    cfg = _W["cfg"] if eps is None else {**_W["cfg"], "A3": {**_W["cfg"]["A3"], "eps": eps}}
    obs, _ = asyncio.run(_run(arm, seed, cfg, suite))
    res = _W["ote"].audit(obs, _ref(suite), cost_usd=audit_cost(obs, _W["prices"]))
    return {"arm": arm, "seed": seed, "eps": eps, "suite": suite,
            "score": None if res.score != res.score else res.score, "cost": res.cost_usd}


def wilson(k, n, z=1.959964):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return f"{p:.0%} [{max(0, c - h):.0%}, {min(1, c + h):.0%}]"


def auroc(pos, neg):
    a, b = np.asarray(pos), np.asarray(neg)
    return float((a[:, None] > b[None, :]).mean() + 0.5 * (a[:, None] == b[None, :]).mean())


def main() -> int:
    protocol = load_sealed(ROOT / "config" / "protocol_v2.yaml")
    sealed_thr = protocol["thresholds"]["mock"]["OTE"]["threshold"]
    probes = disguised_suite()
    flagged, short, dup = check_disguise(probes)
    print(f"disguise check: A5 flags {flagged}/{len(probes)}, short {short}, duplicates {dup}")

    rng = lambda k: range(SEEDS[k][0], SEEDS[k][1] + 1)
    jobs = [("A0", s, None, "disguised") for s in rng("calibration")]
    for suite in ["disguised", "standard"]:
        jobs += [("A0", s, None, suite) for s in rng("holdout")]
        jobs += [(a, s, e, suite) for a, e in ARMS for s in rng("arms")]
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2)), initializer=_init) as ex:
        rows = list(ex.map(job, jobs, chunksize=8))
    print(f"ran {len(rows)} sessions")

    sel = lambda suite, arm, eps=None, seeds="arms": [
        r["score"] for r in rows if r["suite"] == suite and r["arm"] == arm and r["eps"] == eps
        and SEEDS[seeds][0] <= r["seed"] <= SEEDS[seeds][1] and r["score"] is not None]
    cal = sel("disguised", "A0", seeds="calibration")
    thr = {"disguised": max(cal), "standard": sealed_thr}
    cost = {s: float(np.median([r["cost"] for r in rows if r["suite"] == s])) for s in thr}

    L = ["# Disguised probes vs probe-aware evasion (exploratory, NOT sealed)", "",
         "Hand-written mock, OTE only, 8 cells x 30 requests per session. Generated by "
         "`scripts/18_disguised_probes.py`.", "",
         f"Disguise check on the {len(probes)} disguised requests: A5 classifies {flagged} as probes; "
         f"{short} are under A5's length limit; {dup} are duplicates.", "",
         f"Thresholds: standard suite = sealed v2 OTE threshold {thr['standard']:+.4f}; disguised suite = "
         f"max of {len(cal)} fresh honest sessions {thr['disguised']:+.4f} (flag at >).", "",
         f"Median cost per session: standard ${cost['standard']:.4f}, disguised ${cost['disguised']:.4f} "
         f"({cost['disguised'] / cost['standard']:.1f}x).", "",
         "| arm | standard: flagged | standard: AUROC | disguised: flagged | disguised: AUROC |",
         "|---|---|---|---|---|"]
    for arm, eps in [("A0", None)] + ARMS:
        cells = []
        for suite in ["standard", "disguised"]:
            hold = sel(suite, "A0", seeds="holdout")
            xs = hold if arm == "A0" else sel(suite, arm, eps)
            k = sum(x > thr[suite] for x in xs)
            cells += [wilson(k, len(xs)), "-" if arm == "A0" else f"{auroc(xs, hold):.2f}"]
        label = "A0 (honest holdout)" if arm == "A0" else (f"A3 eps={eps}" if eps else arm)
        L.append(f"| {label} | " + " | ".join(cells) + " |")
        print(L[-1])
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
