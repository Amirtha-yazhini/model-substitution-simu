# The confound, quantified: A3 @ eps=0.10 vs A11

Source: 20 sessions each (09_eps_power.py). AUROC(A3 vs A11) of 0.5 means the auditor cannot tell fraud from sanctioned routing; 1.0 means it separates them perfectly.

| Auditor | flag rate A3 | flag rate A11 | AUROC A3 vs A11 |
|---|---|---|---|
| OTE | 15% | 0% | 0.72 |
| IRIS-lite | 35% | 0% | 0.93 |
| GATEOPS | 100% | 100% | 0.00 |
| KBF | 0% | 0% | 0.64 |
| BENCH | 0% | 5% | 0.47 |
| FUSE | 0% | 15% | 0.28 |
