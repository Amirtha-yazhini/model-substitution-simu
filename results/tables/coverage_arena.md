# Auditor applicability across arms

`applicable=False` forces `uninformative`, never `consistent`. An auditor that cannot run is not an auditor that passed.

| Auditor | applicable cells | total | coverage | reason when not |
|---|---|---|---|---|
| OTE | 96 | 96 | 100% | - |
| IRIS-lite | 96 | 96 | 100% | - |
| GATEOPS | 93 | 96 | 97% | needs >=20 timed responses per side (suspect=8, reference=240); replayed corpora |
| KBF | 96 | 96 | 100% | - |
| BENCH | 96 | 96 | 100% | - |
| RUT | 0 | 96 | 0% | endpoint does not expose logprobs |
| FUSE | 96 | 96 | 100% | - |
