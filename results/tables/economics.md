# Economics: audit cost to 80% power vs adversary savings

Protocol `923a3d217470a347...`. Power per session is the fraction of 20 A3 sessions each auditor flags under the SEALED threshold (09_eps_power.py). Sessions needed = smallest k with 1-(1-p)^k >= 0.8, flagging if any session flags; repeating an audit inflates its false-positive rate too, which the admissibility rule below accounts for.

Substitute/genuine price ratio for the session token mix: **0.115**. Adversary saving = $1,000 x eps x (1 - ratio) per month.

An audit is **admissible** only if its family false-positive rate 1-(1-f)^k stays within 5%, where f is the auditor's realised per-session FPR on honest sessions never used for fitting (threshold-audit blocks B and C plus the grid holdout), floored at 1/101.

| Auditor | honest flags | honest sessions | f used | max admissible sessions |
|---|---|---|---|---|
| OTE | 3 | 250 | 1.20% | 4 |
| IRIS-lite | 0 | 250 | 0.99% | 5 |
| GATEOPS | 20 | 250 | 8.00% | 0 |
| KBF | 3 | 250 | 1.20% | 4 |
| BENCH | 6 | 250 | 2.40% | 2 |
| FUSE | 0 | 50 | 0.99% | 5 |

eps* (smallest swept rate where the cheapest ADMISSIBLE audit pays for itself): **0.1**

| Auditor | eps | power/session | audit cost to 80% (USD) | admissible | saving (USD) |
|---|---|---|---|---|---|
| OTE | 0.02 | 0% | >= 0.031 (0/20 detected) | - | 17.70 |
| OTE | 0.05 | 5% | 0.090 | no | 44.24 |
| OTE | 0.1 | 15% | 0.028 | no | 88.49 |
| OTE | 0.25 | 45% | 0.008 | yes | 221.22 |
| OTE | 0.5 | 100% | 0.003 | yes | 442.43 |
| IRIS-lite | 0.02 | 0% | >= 0.016 (0/20 detected) | - | 17.70 |
| IRIS-lite | 0.05 | 0% | >= 0.016 (0/20 detected) | - | 44.24 |
| IRIS-lite | 0.1 | 35% | 0.006 | yes | 88.49 |
| IRIS-lite | 0.25 | 100% | 0.001 | yes | 221.22 |
| IRIS-lite | 0.5 | 100% | 0.001 | yes | 442.43 |
| GATEOPS | 0.02 | 5% | 0.090 | no | 17.70 |
| GATEOPS | 0.05 | 35% | 0.011 | no | 44.24 |
| GATEOPS | 0.1 | 100% | 0.003 | no | 88.49 |
| GATEOPS | 0.25 | 100% | 0.003 | no | 221.22 |
| GATEOPS | 0.5 | 100% | 0.003 | no | 442.43 |
| KBF | 0.02 | 0% | >= 0.014 (0/20 detected) | - | 17.70 |
| KBF | 0.05 | 0% | >= 0.014 (0/20 detected) | - | 44.24 |
| KBF | 0.1 | 0% | >= 0.014 (0/20 detected) | - | 88.49 |
| KBF | 0.25 | 15% | 0.013 | no | 221.22 |
| KBF | 0.5 | 70% | 0.003 | yes | 442.43 |
| BENCH | 0.02 | 5% | 0.081 | no | 17.70 |
| BENCH | 0.05 | 0% | >= 0.028 (0/20 detected) | - | 44.24 |
| BENCH | 0.1 | 0% | >= 0.028 (0/20 detected) | - | 88.49 |
| BENCH | 0.25 | 45% | 0.008 | no | 221.22 |
| BENCH | 0.5 | 90% | 0.003 | yes | 442.43 |
| FUSE | 0.02 | 0% | >= 0.152 (0/20 detected) | - | 17.70 |
| FUSE | 0.05 | 0% | >= 0.152 (0/20 detected) | - | 44.24 |
| FUSE | 0.1 | 0% | >= 0.152 (0/20 detected) | - | 88.49 |
| FUSE | 0.25 | 100% | 0.014 | yes | 221.22 |
| FUSE | 0.5 | 100% | 0.014 | yes | 442.43 |
