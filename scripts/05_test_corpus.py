"""Phase 2 acceptance: record a census, replay it, prove the replay is faithful.

The README claims a reader can clone this repository and reproduce every figure
with no API key. That claim rests entirely on the replay corpus being a faithful
stand-in for the endpoints it recorded, so it gets a test rather than an
assertion.

Checked here:
  1. resume - re-running the census over a complete corpus sends zero requests
  2. round-trip fidelity - replayed text, usage, fingerprint, finish_reason and
     latency match the recorded response exactly, so auditors that read those
     fields are no less applicable on replay than they were live
  3. determinism - two replays of one corpus produce identical observations
  4. the corpus still separates honest from substituted traffic
  5. corpus misses are reported rather than silently passing

Point 4 needs a word. A census buys ONE session per endpoint - 240 requests is 30
repeats per cell, not 30 independent sessions - so the 100-session calibration
that scripts/03_test_ote.py runs on the mock is not affordable against real
endpoints. The permutation p-value is what makes that survivable: it calibrates
against relabellings of the data in hand, so it still says something from a
single recorded session, where a session-level threshold cannot.

No keys, no network, no quota. Runs in seconds.
"""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.auditors.ote import OTEAuditor  # noqa: E402
from arena.collect import collect  # noqa: E402
from arena.corpus import Corpus, CorpusWriter, ReplayBackend  # noqa: E402
from arena.probes.ote_probes import probe_set  # noqa: E402
from shim.gateway import MOCK_LADDER, Gateway  # noqa: E402
from shim.ledger import Ledger, load_prices  # noqa: E402
from shim.mock import MOCK_MODELS, MockBackend  # noqa: E402
from shim.policy import load_arm_config  # noqa: E402
from shim.types import AuditRequest, Endpoint  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPEATS = 60          # split in half gives 30 reference + 30 suspect per cell
HALF = REPEATS // 2
SUITE = "core"


def load_census_module():
    """Load 04_census.py by path - its name is not a valid Python identifier.

    Imported rather than reimplemented on purpose: a round-trip test that
    exercised its own private recorder would prove nothing about the recorder
    the real census actually uses.
    """
    spec = importlib.util.spec_from_file_location(
        "census_mod", ROOT / "scripts" / "04_census.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def replay_gateway(arm: str, corpus: Corpus, ledger_path: Path) -> Gateway:
    return Gateway(
        MOCK_LADDER, arm, ReplayBackend(corpus),
        ledger=Ledger(path=ledger_path, prices=load_prices()),
        arm_cfg=load_arm_config(),
    )


def probe_request(prompt: str, max_tokens: int = 256) -> AuditRequest:
    messages = [{"role": "user", "content": prompt}]
    raw = {"model": MOCK_LADDER.advertised, "messages": messages, "max_tokens": max_tokens}
    return AuditRequest(
        model=MOCK_LADDER.advertised, messages=messages, max_tokens=max_tokens,
        temperature=1.0, top_p=None, logprobs=False, seed=None, raw=raw,
    )


async def main() -> int:
    failures: list[str] = []
    probes = probe_set(SUITE)
    auditor = OTEAuditor()
    census = load_census_module()

    tmp = Path(tempfile.mkdtemp(prefix="shim-corpus-"))
    corpus_dir, ledger_path = tmp / "corpus", tmp / "ledger.jsonl"
    expected = len(probes) * REPEATS

    print("=" * 76)
    print("Phase 2 acceptance: corpus round-trip (no keys, no network, $0)")
    print("=" * 76)

    # ---- 1. record ----
    writer = CorpusWriter(corpus_dir)
    backend = MockBackend(session_seed=7)
    print(f"\nRecording {len(MOCK_MODELS)} mock endpoints x {len(probes)} cells "
          f"x {REPEATS} repeats ...")
    for model in MOCK_MODELS:
        st = await census.census_endpoint(backend, writer, "mock", model, probes, REPEATS)
        if st["ok"] != expected:
            failures.append(f"census: {model} recorded {st['ok']}/{expected}")
    writer.write_manifest({"suite": "ote", "repeats": REPEATS, "mock": True})
    print(f"  wrote {writer.n_written} records")

    # ---- 2. resume must be free ----
    st = await census.census_endpoint(
        backend, writer, "mock", "genuine-70b", probes, REPEATS
    )
    if st["sent"] or st["skipped"] != expected:
        failures.append(f"resume: re-running a complete endpoint sent {st['sent']} requests")
    else:
        print(f"  resume: re-running a complete endpoint sent 0 requests "
              f"({st['skipped']} skipped)")

    # ---- 3. round-trip fidelity ----
    corpus = Corpus.load(corpus_dir)
    print(f"\nLoaded corpus: {corpus.n_records} records across {len(corpus.models)} models")

    recorded = corpus.by_prompt[("genuine-70b", probes[0].prompt)][0]
    replayed = await ReplayBackend(corpus).chat(
        Endpoint("mock", "genuine-70b"),
        {"messages": [{"role": "user", "content": probes[0].prompt}]},
    )
    body = replayed.body or {}
    checks = {
        "text": (recorded["body"]["choices"][0]["message"]["content"], replayed.text),
        "usage": (recorded["body"]["usage"], replayed.usage),
        "system_fingerprint": (recorded["body"].get("system_fingerprint"),
                               body.get("system_fingerprint")),
        "finish_reason": (recorded["body"]["choices"][0].get("finish_reason"),
                          (body.get("choices") or [{}])[0].get("finish_reason")),
        "latency_s": (recorded["latency_s"], round(replayed.latency_s, 4)),
    }
    for name, (want, have) in checks.items():
        if want != have:
            failures.append(f"round-trip: {name} differs ({want!r} vs {have!r})")
    print("  round-trip preserves: " + ", ".join(checks))

    # ---- 4. determinism ----
    ref_corpus, test_corpus = corpus.split(0.5)
    obs_a = await collect(replay_gateway("A0", test_corpus, ledger_path), probes, repeats=HALF)
    obs_b = await collect(replay_gateway("A0", test_corpus, ledger_path), probes, repeats=HALF)
    if [o.text for o in obs_a] != [o.text for o in obs_b]:
        failures.append("determinism: two replays produced different observations")
    else:
        print(f"  determinism: two replays of {len(obs_a)} observations are identical")

    # ---- 5. the signal survives replay ----
    print("\nDoes the replayed corpus still separate honest from substituted traffic?")
    reference = await collect(replay_gateway("A0", ref_corpus, ledger_path), probes, repeats=HALF)

    results = {}
    for arm in ("A0", "A1"):
        obs = await collect(replay_gateway(arm, test_corpus, ledger_path), probes, repeats=HALF)
        res = auditor.audit(obs, reference)
        results[arm] = res
        if not res.applicable:
            failures.append(f"{arm}: uninformative on replay - {res.detail.get('reason')}")
            continue
        print(f"  {arm}: debiased JSD {res.score:+.4f}  raw {res.detail['raw_mean_jsd']:.4f}  "
              f"Fisher p {res.detail['fisher_p']:.2e}  cells {res.detail['n_cells']}")

    if all(r.applicable for r in results.values()):
        a0, a1 = results["A0"], results["A1"]
        # Honest-vs-honest across DISJOINT halves of one recording is the real
        # null here, and the debiased statistic has to sit near zero for it.
        if abs(a0.score) > 0.05:
            failures.append(f"A0 replay null is not near zero ({a0.score:+.4f})")
        if a0.detail["fisher_p"] < 0.01:
            failures.append(f"A0 replay flagged at p={a0.detail['fisher_p']:.2e}")
        if a1.score <= a0.score or a1.detail["fisher_p"] > 0.01:
            failures.append(
                f"A1 not separated on replay (score {a1.score:+.4f} vs {a0.score:+.4f}, "
                f"p={a1.detail['fisher_p']:.2e})"
            )
        else:
            print(f"  -> separation survives replay: A1 {a1.score:+.4f} vs honest "
                  f"{a0.score:+.4f}, p {a1.detail['fisher_p']:.1e}")

    # ---- 6. corpus misses must be visible ----
    rb = ReplayBackend(corpus)
    gw7 = replay_gateway("A7", corpus, ledger_path)
    gw7.backend = rb
    _, row = await gw7.handle(probe_request(probes[0].prompt))
    if row.get("launder_ok") is not False:
        failures.append("A7 on replay should report launder_ok=False")
    else:
        print(f"\n  A7 under replay: launder_ok=False after {rb.misses} corpus miss")
        print("    (expected - the restyle hop sends a prompt no census recorded, so")
        print("     laundering needs live traffic, as GATEOPS latency and A9 do)")

    shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 76)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Corpus round-trip is faithful. Replay is a valid stand-in for the fleet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
