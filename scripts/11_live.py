"""Phase 6 - live confirmation. The only phase after the census that spends quota.

Latency and wire metadata cannot be replayed: the corpus records what a model
SAID, and a replayed timing is a number from the past, not a measurement. So
GATEOPS - and A9, which exists to defeat it - were only ever tested against the
mock backend's invented latency profiles. This run puts real SHIM servers in
front of real Groq endpoints and times them from the client side of an actual
HTTP connection, which is the only place an auditor can stand.

Design choices that decide whether the numbers mean anything:

  * CLIENT-SIDE timing. The auditor sees what `httpx` measures, including SHIM's
    own overhead and A9's real sleep. Ledger fields are recorded for comparison
    but never fed to an auditor.
  * NO QUOTA SLEEP INSIDE SHIM. The shared QuotaManager keeps the daily counter
    but has its per-minute pacing disabled; the client paces instead. Otherwise
    the gateway's rate-limit wait would land inside the timed interval and
    GATEOPS would measure our limiter, not the backend - the same class of bug
    as the wall-clock latency defect fixed in Phase 3.
  * INTERLEAVED arms. Every round sends each probe once to every arm in a seeded
    random order. Groq's latency drifts with load over minutes; running arms in
    sequence would turn that drift into a between-arm difference.
  * PRE-REGISTERED rules. The decision rules are written and hashed to
    results/live/plan.json BEFORE the first request. Nothing is fitted here.

Arms: REF (a second honest server - the reference sample), A0, A1, A3@0.10, A9.
A11 is BLOCKED on this fleet: benign routing needs a second free provider of the
genuine model, and none exists (Cerebras returns 402; OpenRouter lists
gpt-oss-120b only as a paid slug). That is recorded as coverage, not simulated.

    python scripts/11_live.py              # plan and budget only; fires nothing
    python scripts/11_live.py --yes        # the live run (~480 Groq requests, ~25 min)
    python scripts/11_live.py --analyze    # re-score committed observations, no API
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena.auditors.gateops import GateOpsAuditor, cv  # noqa: E402
from arena.auditors.ote import OTEAuditor  # noqa: E402
from arena.base import Observation  # noqa: E402
from arena.probes.ote_probes import probe_set  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "live"
OBS = OUT / "observations.jsonl"
PLAN = OUT / "plan.json"
SUMMARY = OUT / "summary.json"
TABLE = ROOT / "results" / "tables" / "live.md"
FIGURE = ROOT / "results" / "figures" / "F7_live_latency.png"

LADDER = "gptoss_primary"
LABELS = ["REF", "A0", "A1", "A3", "A9"]
ARM_OF = {"REF": "A0", "A0": "A0", "A1": "A1", "A3": "A3", "A9": "A9"}
IS_SUBSTITUTION = {"A0": False, "A1": True, "A3": True, "A9": True}
BLOCKED = {
    "A11": "no second free provider of openai/gpt-oss-120b: cerebras returns HTTP 402 "
           "(re-tested 2026-09-14), openrouter lists it only as a paid slug",
}
REPEATS = 12                    # 8 cells x 12 = 96 requests per arm
PACE_S = 60.0 / (30 * 0.85)     # Groq documents 30 RPM; pace 15% under it
BASE_PORT = 8610
ALPHA = 0.01
MAX_RETRIES = 3

# Mock-grid medians for the same arms (results/tables/grid.md), the prediction
# this run tests. Copied, not recomputed, so the comparison is to what was
# published before any live data existed.
MOCK_GATEOPS_MEDIAN = {"A0": 0.050, "A1": 0.979, "A3": 0.133, "A9": 0.358}


def _load_script(name: str):
    """Import a numbered script (not a valid module name) for reuse."""
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), ROOT / "scripts" / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ----------------------------------------------------------------------
# pre-registration
# ----------------------------------------------------------------------

def build_plan(protocol: dict[str, Any]) -> dict[str, Any]:
    thr = protocol["thresholds"]
    return {
        "phase": 6,
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sealed_protocol_sha256": protocol["sha256"],
        "ladder": LADDER,
        "labels": LABELS,
        "arm_of": ARM_OF,
        "blocked": BLOCKED,
        "probes": "ote core, 8 cells",
        "repeats": REPEATS,
        "requests_planned": len(LABELS) * 8 * REPEATS,
        "timing": "client-side httpx wall time per HTTP request to SHIM",
        "order": "per round, every probe to every label in seeded random order",
        "rules": {
            "gateops_sealed": f"flag if KS statistic >= {thr['GATEOPS']['threshold']} "
                              "(sealed on mock 240-vs-240; transfer test, expected to over-fire at n=96)",
            "gateops_ks_p": f"flag if two-sample KS p < {ALPHA} (calibration-free)",
            "ote_sealed": f"flag if debiased mean JSD >= {thr['OTE']['threshold']} "
                          "(sealed on mock at 30 repeats; transfer test)",
            "ote_fisher_p": f"flag if Fisher-combined permutation p < {ALPHA}",
            "fingerprint": "flag if suspect shows a system_fingerprint the reference never did",
        },
        "null_check": "A0 vs REF must be clean under every calibration-free rule",
        "predictions_from_mock": MOCK_GATEOPS_MEDIAN,
    }


def seal(doc: dict[str, Any]) -> dict[str, Any]:
    blob = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return {**doc, "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest()}


# ----------------------------------------------------------------------
# the live run
# ----------------------------------------------------------------------

async def start_servers(ledger_dir: Path):
    import uvicorn

    from shim.backends import Client, load_providers
    from shim.gateway import LiveBackend
    from shim.quota import QuotaManager, budgets_from_providers
    from shim.server import build_app

    providers = load_providers()
    budgets = budgets_from_providers(providers)
    for b in budgets.values():
        b.rpm = None                # pacing lives in the client; see module docstring
    backend = LiveBackend(Client(timeout=120), providers, QuotaManager(budgets))

    servers, tasks = [], []
    for i, label in enumerate(LABELS):
        app = build_app(
            ARM_OF[label], LADDER, live=True, real_sleep=True,
            ledger_path=ledger_dir / f"ledger_{label}.jsonl", backend=backend,
        )
        server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=BASE_PORT + i, log_level="warning", lifespan="off",
        ))
        servers.append(server)
        tasks.append(asyncio.create_task(server.serve()))
    while not all(s.started for s in servers):
        await asyncio.sleep(0.05)
    return backend, servers, tasks


async def run_live() -> int:
    census = _load_script("04_census.py")
    import httpx

    OUT.mkdir(parents=True, exist_ok=True)
    for f in [OBS, *OUT.glob("ledger_*.jsonl")]:
        f.unlink(missing_ok=True)

    backend, servers, tasks = await start_servers(OUT)
    ports = {label: BASE_PORT + i for i, label in enumerate(LABELS)}
    probes = probe_set("core")
    schedule = []
    rng = random.Random(6)
    for r in range(REPEATS):
        for probe in probes:
            order = LABELS[:]
            rng.shuffle(order)
            schedule += [(r, probe, label) for label in order]

    print(f"Live run: {len(schedule)} requests, pace {PACE_S:.2f}s, "
          f"~{len(schedule) * (PACE_S + 0.6) / 60:.0f} min\n", flush=True)
    t_start = time.perf_counter()
    n_ok = n_fail = n_retry = 0

    async with httpx.AsyncClient(timeout=180) as client:
        with open(OBS, "a", encoding="utf-8") as fh:
            for i, (r, probe, label) in enumerate(schedule):
                body = {
                    "model": "openai/gpt-oss-120b",
                    "messages": [{"role": "user", "content": probe.prompt}],
                    "max_tokens": probe.max_tokens,
                    "temperature": probe.temperature,
                    # Distinct body per repeat, so A3's hash-seeded routing samples.
                    "_repeat": r,
                }
                url = f"http://127.0.0.1:{ports[label]}/v1/chat/completions"
                attempts = 0
                while True:
                    t_sent = time.perf_counter()
                    resp = await client.post(url, json=body)
                    latency = time.perf_counter() - t_sent
                    attempts += 1
                    data = resp.json()
                    if resp.status_code == 200:
                        break
                    err = (data.get("error") or {}).get("message", "")
                    kind, wait = census.classify_error(err)
                    if kind != "transient" or attempts > MAX_RETRIES:
                        break
                    n_retry += 1
                    await asyncio.sleep(max(wait, PACE_S) * 2 ** (attempts - 1))

                ok = resp.status_code == 200
                choice = (data.get("choices") or [{}])[0] if ok else {}
                row = {
                    "i": i, "label": label, "arm": ARM_OF[label], "cell": probe.cell,
                    "repeat": r, "ok": ok, "status": resp.status_code,
                    "attempts": attempts, "client_latency_s": round(latency, 4),
                    "text": (choice.get("message") or {}).get("content") if ok else None,
                    "finish_reason": choice.get("finish_reason"),
                    "usage": data.get("usage") if ok else None,
                    "system_fingerprint": data.get("system_fingerprint") if ok else None,
                    "model_echoed": data.get("model") if ok else None,
                    "error": None if ok else (data.get("error") or {}).get("message", "")[:400],
                    "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                n_ok += ok
                n_fail += not ok
                if (i + 1) % 25 == 0 or not ok:
                    mins = (time.perf_counter() - t_start) / 60
                    print(f"  {i + 1:>4}/{len(schedule)}  ok={n_ok} fail={n_fail} "
                          f"retries={n_retry}  {mins:.1f} min"
                          + (f"  [{label}] {row['error'][:100]}" if not ok else ""), flush=True)
                if not ok and "quota" in (row["error"] or "").lower() and "exhaust" in row["error"].lower():
                    print("  daily quota exhausted - stopping; --analyze scores what was collected")
                    break
                await asyncio.sleep(PACE_S)

    for s in servers:
        s.should_exit = True
    await asyncio.gather(*tasks)
    await backend.client.aclose()
    print(f"\nDone: ok={n_ok} fail={n_fail} retries={n_retry} "
          f"in {(time.perf_counter() - t_start) / 60:.1f} min")
    return 0


# ----------------------------------------------------------------------
# analysis
# ----------------------------------------------------------------------

def load_observations() -> dict[str, list[Observation]]:
    out: dict[str, list[Observation]] = {label: [] for label in LABELS}
    for line in OBS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        out[row["label"]].append(Observation(
            probe_id=f"{row['cell']}#{row['repeat']}", cell=row["cell"], text=row["text"],
            latency_s=row["client_latency_s"] if row["ok"] else 0.0,
            usage=row["usage"] or {}, system_fingerprint=row["system_fingerprint"],
            finish_reason=row["finish_reason"], ok=row["ok"],
        ))
    return out


def ground_truth() -> dict[str, dict[str, Any]]:
    """Per label, from the ledgers - which no auditor reads."""
    out = {}
    for label in LABELS:
        rows = [json.loads(x) for x in
                (OUT / f"ledger_{label}.jsonl").read_text(encoding="utf-8").splitlines()]
        ok = [r for r in rows if r["ok"]]
        out[label] = {
            "ledger_rows": len(rows),
            "substituted": sum(1 for r in ok if not r["is_genuine"]),
            "served": len(ok),
            "backends": sorted({r["true_model"] for r in ok}),
            "median_backend_latency_s": statistics.median(r["backend_latency_s"] for r in ok) if ok else None,
            "median_injected_latency_s": statistics.median(r["injected_latency_s"] for r in ok) if ok else None,
        }
    return out


def analyze() -> int:
    grid = _load_script("07_grid.py")
    protocol = grid.load_protocol()          # verifies the Phase 4 seal
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    obs = load_observations()
    truth = ground_truth()
    thr = protocol["thresholds"]

    gate = GateOpsAuditor(threshold=thr["GATEOPS"]["threshold"])
    ote = OTEAuditor(threshold=thr["OTE"]["threshold"], n_perm=protocol["conditions"]["ote_permutations"])
    ref = obs["REF"]

    results: dict[str, Any] = {}
    for label in LABELS:
        s = obs[label]
        lat = [o.latency_s for o in s if o.ok]
        row: dict[str, Any] = {
            "arm": ARM_OF[label],
            "n_ok": len(lat), "n_failed": sum(1 for o in s if not o.ok),
            "median_latency_s": statistics.median(lat) if lat else None,
            "p90_latency_s": sorted(lat)[int(0.9 * (len(lat) - 1))] if lat else None,
            "cv": cv(lat),
            "truth": truth[label],
        }
        if label != "REF":
            g = gate.audit(s, ref)
            o = ote.audit(s, ref)
            gd, od = g.detail, o.detail
            row["gateops"] = {
                "applicable": g.applicable,
                "ks": None if not g.applicable else g.score,
                "ks_p": gd.get("latency_ks_p"),
                "flag_sealed": g.applicable and g.score >= thr["GATEOPS"]["threshold"],
                "flag_ks_p": g.applicable and gd["latency_ks_p"] < ALPHA,
                "fingerprints": gd.get("fingerprints_suspect"),
                "fingerprint_novel": gd.get("fingerprint_novel"),
                "flag_fingerprint": bool(gd.get("fingerprint_novel")),
                "reason": gd.get("reason"),
            }
            row["ote"] = {
                "applicable": o.applicable,
                "jsd": None if not o.applicable else o.score,
                "fisher_p": od.get("fisher_p"),
                "flag_sealed": o.applicable and o.score >= thr["OTE"]["threshold"],
                "flag_fisher_p": o.applicable and od["fisher_p"] < ALPHA,
                "n_cells": od.get("n_cells"),
                "suspect_modes": od.get("suspect_modes"),
                "reason": od.get("reason"),
            }
        results[label] = row

    ref_fp = sorted({o.system_fingerprint for o in ref if o.system_fingerprint})
    summary = {
        "plan_sha256": plan["sha256"],
        "protocol_sha256": protocol["sha256"],
        "reference_fingerprints": ref_fp,
        "blocked": BLOCKED,
        "labels": results,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_table(summary, plan, thr)
    write_figure(obs)
    print(TABLE.read_text(encoding="utf-8"))
    return 0


def _f(x, fmt="{:.3f}"):
    return "-" if x is None or x != x else fmt.format(x)


def _flag(b: bool, applicable: bool = True) -> str:
    # An auditor that could not run is uninformative, never a pass.
    if not applicable:
        return "u"
    return "**F**" if b else "."


def write_table(summary, plan, thr) -> None:
    res = summary["labels"]
    L = [
        "# Phase 6: live confirmation on Groq\n",
        f"Ladder `{LADDER}`: advertised `openai/gpt-oss-120b`, substitute `openai/gpt-oss-20b`, "
        f"both on Groq. {REPEATS} repeats x 8 OTE cells per arm, arms interleaved in random "
        "order each round, latency timed by the client over real HTTP to a SHIM server.\n",
        f"Decision rules pre-registered in `results/live/plan.json` (SHA-256 `{plan['sha256'][:16]}...`) "
        f"before the first request. Sealed thresholds from protocol `{summary['protocol_sha256'][:16]}...`, "
        "unmodified. **F** = flagged.\n",
        "## What the endpoints actually did (ground truth, from the ledgers)\n",
        "| Label | arm | served | substituted | client median s | client p90 s | CV | backend median s | injected median s |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for label in LABELS:
        r, t = res[label], res[label]["truth"]
        L.append(f"| {label} | {r['arm']} | {r['n_ok']} (+{r['n_failed']} failed) | {t['substituted']} | "
                 f"{_f(r['median_latency_s'])} | {_f(r['p90_latency_s'])} | {_f(r['cv'], '{:.2f}')} | "
                 f"{_f(t['median_backend_latency_s'])} | {_f(t['median_injected_latency_s'])} |")

    L += [
        "",
        "## Auditor decisions against REF\n",
        f"GATEOPS sealed rule: KS >= {thr['GATEOPS']['threshold']:.3f}. OTE sealed rule: debiased JSD >= "
        f"{thr['OTE']['threshold']:.4f}. Both were calibrated on the mock backend at larger n, so their "
        f"live use is a transfer test. The `p < {ALPHA}` columns need no calibration.\n",
        "| Arm | truth | GATEOPS KS | KS p | sealed | p-rule | mock KS (predicted) | novel fingerprint | OTE JSD | Fisher p | sealed | p-rule |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for label in LABELS[1:]:
        r = res[label]
        g, o = r["gateops"], r["ote"]
        truth = "**substitution**" if IS_SUBSTITUTION[r["arm"]] else "genuine"
        fp = ", ".join(g["fingerprint_novel"] or []) or "none"
        L.append(
            f"| {label} | {truth} | {_f(g['ks'])} | {_f(g['ks_p'], '{:.1e}')} | "
            f"{_flag(g['flag_sealed'], g['applicable'])} | {_flag(g['flag_ks_p'], g['applicable'])} | "
            f"{MOCK_GATEOPS_MEDIAN[r['arm']]:.3f} | "
            f"{_flag(g['flag_fingerprint'], g['applicable'])} `{fp}` | {_f(o['jsd'], '{:+.4f}')} | "
            f"{_f(o['fisher_p'], '{:.1e}')} | {_flag(o['flag_sealed'], o['applicable'])} | "
            f"{_flag(o['flag_fisher_p'], o['applicable'])} |"
        )
    L += [
        "",
        f"Reference fingerprints: `{', '.join(summary['reference_fingerprints']) or 'none'}`.\n",
        "## Blocked\n",
    ]
    L += [f"- **{arm}**: {why}. Recorded as a coverage result; not simulated." for arm, why in BLOCKED.items()]
    TABLE.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_figure(obs) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Palette and styling mirror scripts/10_figures.py.
    surface, ink, ink2, muted, grid, axis = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
    colors = {"REF": ink2, "A0": "#2a78d6", "A1": "#eb6834", "A3": "#1baf7a", "A9": "#e87ba4"}
    plt.rcParams.update({
        "figure.facecolor": surface, "axes.facecolor": surface, "savefig.facecolor": surface,
        "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10,
        "text.color": ink, "axes.labelcolor": ink2, "axes.edgecolor": axis,
        "xtick.color": muted, "ytick.color": muted, "axes.spines.top": False, "axes.spines.right": False,
    })
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for label in LABELS:
        lat = sorted(o.latency_s for o in obs[label] if o.ok)
        if not lat:
            continue
        ys = [(i + 1) / len(lat) for i in range(len(lat))]
        ax.step(lat, ys, where="post", color=colors[label], lw=2.2 if label == "REF" else 1.6,
                ls="--" if label == "REF" else "-", label=f"{label} (median {statistics.median(lat):.2f}s)")
    ax.set_xscale("log")
    ax.set_xlabel("client-observed latency per request (s, log scale)")
    ax.set_ylabel("cumulative fraction of requests")
    ax.set_title("F7  Live latency through SHIM on Groq: what GATEOPS actually sees",
                 loc="left", fontsize=11, color=ink)
    ax.grid(True, color=grid, lw=0.6)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    fig.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=160)
    plt.close(fig)


# ----------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 6 live confirmation run.")
    ap.add_argument("--yes", action="store_true", help="fire the live run (spends Groq quota)")
    ap.add_argument("--analyze", action="store_true", help="score committed observations; no API calls")
    args = ap.parse_args()

    if args.analyze:
        return analyze()

    protocol = _load_script("07_grid.py").load_protocol()
    plan = seal(build_plan(protocol))
    n = plan["requests_planned"]
    print("=" * 78)
    print("Phase 6 - live confirmation")
    print("=" * 78)
    print(f"  sealed protocol {protocol['sha256'][:24]}... VERIFIED")
    print(f"  ladder {LADDER}; labels {', '.join(LABELS)}; blocked {', '.join(BLOCKED)}")
    print(f"  {n} Groq requests (+ retries), ~{n * (PACE_S + 0.6) / 60:.0f} min, $0")
    if not args.yes:
        print("\nDry run. Nothing fired. Re-run with --yes.")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"  plan pre-registered: {PLAN.relative_to(ROOT)} sha256 {plan['sha256'][:24]}...\n")
    rc = asyncio.run(run_live())
    return rc or analyze()


if __name__ == "__main__":
    raise SystemExit(main())
