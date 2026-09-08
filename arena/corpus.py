"""The replay corpus: recorded free-tier responses, and a backend that serves them.

This module is what makes the reproducibility claim true rather than aspirational.
Free-tier quota is the binding resource in this project - the whole fleet gives
roughly 3,000 requests a day - so an evaluation grid that had to hit live
endpoints could be run about once. Recording every probe response once and
replaying it forever converts a quota problem into a disk problem.

It also removes a second, quieter threat to validity. Live endpoints drift:
providers roll engine versions, swap quantizations and change samplers without
notice. Two auditors evaluated against live traffic a day apart are not evaluated
against the same thing, and any difference between them is confounded with
whatever the provider did overnight. Replay pins the fleet to one instant.

The corpus is COMMITTED to git. A reader clones the repository and reproduces
every figure with no API key and no account.

Layout:
    corpus/<provider>__<model>.jsonl    one record per probe response
    corpus/manifest.json                 summary + provenance

Records are content-addressed by sha256(provider, model, probe_id, repeat), which
is what makes an interrupted census resumable: re-running skips keys already on
disk, so a run that dies at request 51 costs 51 requests, not the whole day.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shim.types import BackendResponse, Endpoint

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = ROOT / "corpus"


def record_key(provider: str, model: str, probe_id: str, repeat: int) -> str:
    """Content address for one probe response."""
    return hashlib.sha256(
        f"{provider}|{model}|{probe_id}|{repeat}".encode("utf-8")
    ).hexdigest()


def _filename(provider: str, model: str) -> str:
    """Model slugs contain '/' and ':', which are not portable in filenames."""
    safe = model.replace("/", "__").replace(":", "-").replace("\\", "__")
    return f"{provider}__{safe}.jsonl"


# ----------------------------------------------------------------------
# write side
# ----------------------------------------------------------------------

class CorpusWriter:
    """Append-only recorder. One JSONL file per endpoint."""

    def __init__(self, root: Path | None = None):
        self.root = root or DEFAULT_CORPUS
        self.root.mkdir(parents=True, exist_ok=True)
        self._handles: dict[str, Any] = {}
        self.n_written = 0

    def path_for(self, provider: str, model: str) -> Path:
        return self.root / _filename(provider, model)

    def existing_keys(self, provider: str, model: str) -> set[str]:
        """Keys already on disk for this endpoint - the resume mechanism.

        Read back from the records themselves rather than from the manifest, so
        a manifest that is stale or missing can never cause a probe to be
        skipped or double-charged.
        """
        path = self.path_for(provider, model)
        if not path.exists():
            return set()
        keys = set()
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    keys.add(json.loads(line)["key"])
                except Exception:
                    continue  # a truncated final line just gets re-probed
        return keys

    def write(
        self, *, provider: str, model: str, suite: str, cell: str,
        probe_id: str, repeat: int, prompt: str, max_tokens: int,
        temperature: float | None, response: BackendResponse,
    ) -> dict[str, Any]:
        rec = {
            "key": record_key(provider, model, probe_id, repeat),
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "provider": provider,
            "model": model,
            "suite": suite,
            "cell": cell,
            "probe_id": probe_id,
            "repeat": repeat,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "ok": response.ok,
            "error": response.error,
            "latency_s": round(response.latency_s, 4),
            # The FULL body, not just the text. Auditors read usage,
            # system_fingerprint and finish_reason; a corpus that kept only the
            # string would silently make those auditors inapplicable on replay.
            "body": response.body,
        }
        path = self.path_for(provider, model)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.n_written += 1
        return rec

    def write_manifest(self, extra: dict[str, Any] | None = None) -> Path:
        """Summarise what is on disk. Provenance, not an index."""
        endpoints: dict[str, Any] = {}
        for path in sorted(self.root.glob("*.jsonl")):
            n = ok = 0
            cells: dict[str, int] = {}
            provider = model = None
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    n += 1
                    ok += 1 if r.get("ok") else 0
                    cells[r.get("cell", "?")] = cells.get(r.get("cell", "?"), 0) + 1
                    provider, model = r.get("provider"), r.get("model")
            if provider is None:
                continue
            endpoints[f"{provider}:{model}"] = {
                "file": path.name,
                "records": n,
                "ok": ok,
                # Failures are kept, not dropped: they ARE the coverage metric.
                "failed": n - ok,
                "cells": dict(sorted(cells.items())),
            }
        manifest = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "endpoints": endpoints,
            "total_records": sum(e["records"] for e in endpoints.values()),
            **(extra or {}),
        }
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return path


# ----------------------------------------------------------------------
# read side
# ----------------------------------------------------------------------

@dataclass
class Corpus:
    """Recorded responses, indexed for replay."""

    root: Path
    # (model, prompt) -> ordered list of records, in the order they were recorded
    by_prompt: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path | None = None) -> "Corpus":
        root = root or DEFAULT_CORPUS
        c = cls(root=root)
        for path in sorted(root.glob("*.jsonl")):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    c.by_prompt.setdefault((r["model"], r["prompt"]), []).append(r)
        # Recorded order is the sampling order. Sorting by repeat makes replay
        # independent of how the census interleaved its requests.
        for recs in c.by_prompt.values():
            recs.sort(key=lambda r: r.get("repeat", 0))
        return c

    def split(self, fraction: float = 0.5) -> tuple["Corpus", "Corpus"]:
        """Split each prompt's recorded samples into two disjoint halves.

        Necessary because a census yields ONE session per endpoint: 240 requests
        buys 30 repeats per cell, not 30 independent sessions. Scoring an
        endpoint against itself would compare a sample to itself and return
        exactly zero, which is not a null - it is a tautology. Splitting the
        repeats gives a genuine reference/suspect pair out of one recording.

        The halves are disjoint by construction, so no observation is ever both
        reference and evidence.
        """
        a, b = Corpus(root=self.root), Corpus(root=self.root)
        for key, recs in self.by_prompt.items():
            cut = int(len(recs) * fraction)
            a.by_prompt[key] = recs[:cut]
            b.by_prompt[key] = recs[cut:]
        return a, b

    @property
    def n_records(self) -> int:
        return sum(len(v) for v in self.by_prompt.values())

    @property
    def models(self) -> list[str]:
        return sorted({m for m, _ in self.by_prompt})


class ReplayBackend:
    """Serves recorded responses. Drop-in for LiveBackend and MockBackend.

    Repeated identical prompts walk the recorded samples in order, exactly as
    MockBackend's per-prompt counter does, so a replayed session reproduces the
    original response SEQUENCE and not merely its distribution.
    """

    def __init__(self, corpus: Corpus, *, strict: bool = False, wrap: bool = True):
        self.corpus = corpus
        self.strict = strict
        self.wrap = wrap
        self._draw: dict[tuple[str, str], int] = {}
        self.calls = 0
        self.misses = 0
        # Wrapping past the end reuses samples. That is fine for a smoke test and
        # NOT fine for a power calculation, so it is counted and reported rather
        # than hidden: reused draws are not independent observations.
        self.reused = 0

    def _miss(self, endpoint: Endpoint, why: str) -> BackendResponse:
        self.misses += 1
        if self.strict:
            raise KeyError(f"corpus miss: {why}")
        return BackendResponse(
            ok=False, body=None, latency_s=0.0, endpoint=endpoint,
            error=f"corpus miss: {why}",
        )

    async def chat(
        self, endpoint: Endpoint, payload: dict[str, Any], *, nonce: int = 0
    ) -> BackendResponse:
        self.calls += 1
        messages = payload.get("messages") or []
        prompt = "\n".join(
            m.get("content", "") for m in messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        )

        recs = self.corpus.by_prompt.get((endpoint.model, prompt))
        if not recs:
            # Expected for A7: the laundering hop sends a restyle prompt that no
            # census recorded. The arm is honestly marked as un-laundered rather
            # than being credited with an evasion it never performed.
            return self._miss(endpoint, f"{endpoint.model} has no record for this prompt")

        key = (endpoint.model, prompt)
        i = self._draw.get(key, 0)
        self._draw[key] = i + 1
        if i >= len(recs):
            if not self.wrap:
                return self._miss(endpoint, f"{endpoint.model} exhausted after {len(recs)} draws")
            self.reused += 1
            i = i % len(recs)

        r = recs[i]
        return BackendResponse(
            ok=bool(r.get("ok")),
            body=r.get("body"),
            latency_s=float(r.get("latency_s") or 0.0),
            endpoint=endpoint,
            error=r.get("error"),
        )

    def report(self) -> str:
        return (
            f"replay: {self.calls} calls, {self.misses} misses, "
            f"{self.reused} reused draws over {self.corpus.n_records} records"
        )
