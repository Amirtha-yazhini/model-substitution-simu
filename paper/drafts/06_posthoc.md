# Checks Added After Sealing

> NOTE: budget 0.75 pages. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

These checks were designed after the sealed results were known, to test how far those results hold
(Tab. posthoc). None changes a sealed number; all are exploratory.

> TABLE posthoc caption: Checks added after sealing (exploratory).

| Question | Result | Caveat |
|---|---|---|
| Cost of hiding (A5) | 3.3% of 172,418 WildChat requests (0.6% of cost) look like tests | API traffic may differ: 76% of Azure code-completion requests generate $\le$24 tokens [@splitwise2024] |
| Disguised tests | OTE catches A5 in every session, at 4.9$\times$ the cost | True by construction in our simulator |
| Sensitivity of $\epsilon^*$ | 0.07–0.15 for power 50–90% and false-alarm budget 1–10% | 0.25 without IRIS-lite at 1% |
| Pooled sessions | KBF catches $\epsilon = 0.05$ with 256–512 sessions (\$0.34–\$0.68 + calibration) | Flags 9–11% of honest routing; never reaches 0.03 |
| Honest timing drift | Yes, within 25 minutes (KS 0.20, $p = 0.046$) | Pooled timing needs concurrent calibration |
| Confound vs. invented timing | At the measured 18% gap GATEOPS still flags 74–100% of A11 | At no gap it flags none |

**Hiding and disguise.** We replayed one of WildChat's fourteen shards through A5's classifier:
on chat traffic A5 keeps over 99% of the saving of always cheating. Asking OTE's questions inside 30
everyday framings we wrote, never repeated, defeats A5 in simulation, but only because our simulator
answers from the question alone; real models answer in prose and may shift with context, and IRIS
finds they stay only partly identifiable across framings [@iris2026]. Disguise does not help
against a gateway that targets auditing accounts.

**Pooling.** One one-sided Welch $t$-test (the simplest test that allows for noise in both
samples) of $k$ sessions' mean score against 300 honest calibration sessions keeps false alarms near
5%. Pooled, GATEOPS catches $\epsilon = 0.02$–$0.03$ and BENCH 0.03, but pooled GATEOPS flags every
honest load-balancing audit and pooled BENCH misses every benchmark-aware A10; IRIS-lite flags every
honest sampling change (A4) and cannot separate the real models. KBF alone passes both checks, so we
simulated 1,000 more sessions per case for it (the sealed run has 200); A5 still beats it.
