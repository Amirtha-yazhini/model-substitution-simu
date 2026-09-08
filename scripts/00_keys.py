"""Report which free-tier keys are configured, and what is still missing.

Reads nothing but .env and config/providers.yaml. Makes zero API calls, so it
costs zero quota. Run this before 01_limits.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shim.backends import load_providers  # noqa: E402

ROLE_LABEL = {
    "primary_workhorse": "REQUIRED  (census engine)",
    "secondary_workhorse": "REQUIRED  (census + latency baseline)",
    "first_party_reference": "REQUIRED  (ground truth)",
    "breadth": "recommended (model variety)",
    "rationed": "recommended (A11 Auto Exacto arm)",
    "overflow": "optional",
}


def main() -> int:
    providers = load_providers()

    have, missing_required, missing_optional = [], [], []
    for p in providers.values():
        label = ROLE_LABEL.get(p.role, p.role)
        if p.configured:
            have.append((p, label))
        elif not p.enabled or p.role == "overflow":
            missing_optional.append((p, label))
        elif p.role in ("breadth", "rationed"):
            missing_optional.append((p, label))
        else:
            missing_required.append((p, label))

    print("=" * 72)
    print("SHIM / Phase 0 - free-tier key check")
    print("=" * 72)

    if have:
        print(f"\nCONFIGURED ({len(have)}):")
        for p, label in have:
            print(f"  [ok]   {p.name:<12} {label}")

    if missing_required:
        print(f"\nMISSING - REQUIRED ({len(missing_required)}):")
        for p, label in missing_required:
            print(f"  [ ]    {p.name:<12} {label}")
            print(f"         env: {p.env_key}")
            print(f"         signup: {p.meta.get('signup', '(see providers.yaml)')}")

    if missing_optional:
        print(f"\nMISSING - optional ({len(missing_optional)}):")
        for p, label in missing_optional:
            print(f"  [ ]    {p.name:<12} {label}  -> {p.env_key}")

    print("\n" + "-" * 72)
    if missing_required:
        print("Next: create the missing REQUIRED accounts (all free, no card),")
        print("      copy .env.example to .env, paste the keys in, re-run this.")
        return 1

    print("All required keys present. Next: python scripts/01_limits.py --yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
