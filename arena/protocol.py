"""Sealed-protocol helpers shared by the v2 scripts.

The hash rule is the one v1 was sealed with (scripts/06_calibrate.py): SHA-256
over the canonical JSON of every field except `sha256` itself. Keeping it
identical means v1 and v2 seals are checked by the same function.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CRLF, LF = bytes([13, 10]), bytes([10])


def protocol_hash(doc: dict[str, Any]) -> str:
    body = {k: v for k, v in doc.items() if k != "sha256"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """SHA-256 of a text file with line endings normalised to LF.

    git (core.autocrlf) stores LF and a Windows checkout writes CRLF, so a raw
    byte hash would break the seal on every other platform.
    """
    return hashlib.sha256(Path(path).read_bytes().replace(CRLF, LF)).hexdigest()


def load_sealed(path: Path) -> dict[str, Any]:
    """Load a protocol and refuse if its seal no longer matches its contents.

    For v2 the fitted-mock file is part of the seal too: editing
    config/mock_fit.yaml after sealing would change every mock-fit number while
    leaving the protocol file itself untouched.
    """
    if not path.exists():
        raise SystemExit(f"{path.name} missing - run scripts/13_protocol_v2.py --write")
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    got = protocol_hash(doc)
    if got != doc.get("sha256"):
        raise SystemExit(
            f"PROTOCOL SEAL BROKEN ({path.name})\n  recorded: {doc.get('sha256')}\n"
            f"  actual:   {got}\nThe file was edited after sealing."
        )
    for rel, want in (doc.get("sealed_inputs") or {}).items():
        have = file_sha256(ROOT / rel)
        if have != want:
            raise SystemExit(
                f"SEALED INPUT CHANGED: {rel}\n  sealed: {want}\n  actual: {have}"
            )
    return doc


def decide(name: str, a: dict[str, Any], thresholds: dict[str, Any], alpha: float) -> str:
    """v2 decision rule on one raw auditor result from arena/batch.py.

    Score auditors flag STRICTLY above the sealed maximum; FUSE flags at
    e >= 1/alpha, which is exactly Ville's inequality and needs no fitting.
    """
    if not a.get("applicable"):
        return "uninformative"
    if name == "FUSE":
        return "inconsistent" if (a.get("e_value") or 0) >= 1.0 / alpha else "consistent"
    thr = (thresholds.get(name) or {}).get("threshold")
    if thr is None or a.get("score") is None:
        return "uninformative"
    return "inconsistent" if a["score"] > thr else "consistent"
