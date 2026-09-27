# Related Work

> NOTE: budget 0.5 pages (~380 words). This draft is ~400.
> NOTE: IRIS is the closest prior work; the paragraph on it must stay precise and fair.

**Detectors by signal.** *Content* detectors compare response text against a reference.
Bruckner's one-token test [@bruckner2026] asks closed questions ("a number from 1 to 100") under a
16-token cap and scores the Jensen-Shannon divergence between answer distributions; it covered 165
models for \$34 with an EER of 7.3%, or 10.6% at the reduced 8-cell operating point we use. KBF
[@fang2026kbf] probes numeric facts near a model's knowledge boundary, where sizes of one family
disagree, and reports catching 5–10% dilution with no false positives across 16 endpoints. IRIS
[@iris2026] trains a random forest on 179 visible-string features and runs a budgeted sequential
plan against OpenRouter models, including dilution. *Operational* detectors use metadata. GateScope
[@lin2026gatescope] audits ten commercial gateways along four axes: content, 25-turn memory, billing
residuals and latency coefficient of variation. *Benchmark* detectors [@cai2025] compare accuracy
on MMLU, GPQA and GSM8K; the same paper finds software-only auditing unreliable and recommends
trusted execution environments. *Logit* detectors need more access: RUT [@zhu2025rut] tests the rank
uniformity of emitted tokens under a locally deployed reference, and DiFR [@difr2025] verifies
inference from raw logits despite nondeterminism. Provenance methods [@stemma2026] and
architecture inference [@archinfer2026] address the related question of what a model is, not whether
it changed.

**Replication.** A frozen-threshold holdout study [@holdout2026] matched model lineage by
`usage.prompt_tokens`. Development pairs separated perfectly; on holdout pairs sensitivity fell to
0.50, and only 6 of 12 pairs could be scored because of rate limits and missing fields. We adopt its
discipline of sealing thresholds before evaluation, and extend it from one method to six.

**The gap.** Each detector was evaluated against a passive gateway that substitutes without regard to
who is asking. None was tested against a gateway that recognises audit traffic, and none was run on
the same data as the others. IRIS is closest to our setting, since it already treats dilution and
audit budget. We differ in three ways: an adaptive adversary, a common replayed corpus on which all
auditors see byte-identical responses, and a benign-routing control that no prior evaluation
includes. Commercial routers already split traffic across providers by default [@openrouter_exacto],
so a detector that flags heterogeneity will flag them.

> REFERENCES (Claude builds refs.bib from these and checks each exists):
> - cai2025: Cai, Shi, Zhao, Song. Are You Getting What You Pay For? Auditing Model Substitution in LLM APIs. arXiv:2504.04715
> - zhu2025rut: Zhu et al. Auditing Black-Box LLM APIs with a Rank-Based Uniformity Test. arXiv:2506.06975
> - lin2026gatescope: Lin et al. Behavioral Consistency and Transparency Analysis on LLM API Gateways (GateScope). IMC'26. arXiv:2604.21083
> - fang2026kbf: Fang et al. KBF: Knowledge Boundary as Fingerprint. arXiv:2605.29524
> - bruckner2026: Bruckner. One Token Is Enough. arXiv:2607.10252
> - iris2026: IRIS: Budgeted Black-Box Auditing of Model Substitution and Routing Dilution in LLM Gateways. arXiv:2607.20860
> - difr2025: DiFR: Inference Verification Despite Nondeterminism. arXiv:2511.20621
> - holdout2026: Token Counts Are Not Model Lineage: A Frozen-Threshold Holdout Study. arXiv:2608.29930
> - stemma2026: Stemma: Induced Decision Regions Reveal LLM Provenance. arXiv:2607.25880
> - archinfer2026: Black-Box Inference of LLM Architectural Properties with Restrictive API Access. arXiv:2607.01313
> - openrouter_exacto: OpenRouter. Auto Exacto: Adaptive Quality Routing, On by Default. https://openrouter.ai/blog/announcements/auto-exacto/
> - vovk2021evalues: Vovk, Wang. E-values: Calibration, combination and applications. Annals of Statistics, 2021.
> - ville1939: Ville. Étude critique de la notion de collectif. 1939.
> - wilson1927: Wilson. Probable inference, the law of succession, and statistical inference. JASA, 1927.
