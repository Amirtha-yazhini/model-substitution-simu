# Threshold audit: how much tail mass does each sealed threshold actually leave?

Protocol `923a3d217470a347be94fbef29f419f7...` claims a conformal false-positive bound of **0.99%**, obtained by taking each threshold as the MAXIMUM over 100 honest calibration sessions.

The table below measures, for each threshold, the fraction of honest sessions in three INDEPENDENT blocks that exceed it. The first block is the one the threshold was fitted on, so its tail is near zero by construction. The other two were never used to fit anything.

| Auditor | sealed threshold | sealed calibration (100-199) | block B (400-499) | block C (9000-9099) |
|---|---|---|---|---|
| OTE | +0.0152 | 0.0% | 3.0% | 0.0% |
| IRIS-lite | +0.1000 | 0.0% | 0.0% | 0.0% |
| GATEOPS | +0.1000 | 0.0% | 9.0% | 6.0% |
| KBF | +0.1600 | 0.0% | 0.0% | 1.0% |
| BENCH | +0.0167 | 0.0% | 2.0% | 2.0% |

## Reading this

A conformal maximum bounds the false-positive rate **marginally** - averaged over which calibration set you happen to draw. Conditional on the one you sealed, the realised rate is a random variable, Beta(1, N)-distributed for a continuous statistic. At N=100 that puts a 10% realised rate at roughly one chance in a million, so a 10% result is not explained by ordinary bad luck.

It is explained by DISCRETENESS. The two-sample KS statistic on 240-vs-240 observations moves in steps of 1/240, and its null distribution piles substantial mass on each step. The maximum of 100 draws therefore lands on a step that still has real probability above it, and the effective tail is set by the step, not by the sample size. OTE's permutation-debiased statistic is near-continuous and shows no such effect; GATEOPS' KS statistic and KBF's agreement rate, both coarse discrete quantities, do.

The fix is not a bigger N - it is a threshold estimator that accounts for the step size, or a statistic that is not coarsely discrete at this sample size. **That change is NOT applied here.** It would require re-sealing, and the point of Phase 4 is that the numbers get reported as they came. This is recorded as a finding about conformal calibration on discrete statistics, and as the first entry on the list of what a protocol v2 should change.

