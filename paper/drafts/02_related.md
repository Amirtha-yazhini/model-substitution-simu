# Related Work

> NOTE: budget 0.5 pages. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

**Auditors, grouped by what they look at.** *Text-based* auditors compare answers with a
reference. Bruckner's one-token test [@bruckner2026] asks short closed questions ("pick a
number from 1 to 100"), caps answers at 16 tokens, and measures how different the two answer
distributions are (Jensen–Shannon divergence). It covered 165 models for \$34, with an equal error
rate of 7.3%, or 10.6% in the smaller 8-question version we use. KBF [@fang2026kbf] asks for
numeric facts that sit at the edge of what a model knows, where large and small models of the same
family disagree; it reports catching 5–10% dilution with no false alarms on 16 endpoints.
IRIS [@iris2026] trains a classifier on 179 surface features of the text and plans its queries
within a budget; it also studies dilution. *Metadata-based* auditors look at how the service
behaves. GateScope [@lin2026gatescope] audited ten commercial gateways using text, 25-turn memory,
billing mismatches and variation in response time. *Benchmark-based*
auditors [@cai2025] compare accuracy on standard tests (MMLU, GPQA, GSM8K); the same paper
concludes that software-only auditing is unreliable and recommends secure hardware.
*Probability-based* auditors need deeper access: RUT [@zhu2025rut] checks the emitted tokens
against a reference model that the auditor runs locally, and DiFR [@difr2025] needs the raw
model scores (logits). Other work identifies what a model is [@stemma2026; @archinfer2026], rather
than whether it was swapped.

**Replication.** A study that fixed its thresholds before testing [@holdout2026] matched
models by their reported prompt token counts. It was perfect on development data, but on fresh data
it caught only half of the substitutions, and 6 of 12 fresh cases could not be scored because of
rate limits and missing fields. We follow its practice of fixing thresholds in advance, and apply it
to six methods instead of one.

**What is missing.** Every auditor was tested against a gateway that cheats the same way no
matter who is asking. None was tested against a gateway that recognises test traffic, and no two
were run on the same data. IRIS is the closest to our work, since it also studies dilution and
audit budgets. We add three things: a cheater that adapts, one shared set of recorded responses that
every auditor sees byte for byte, and an honest load-balancing case that no earlier evaluation
includes. Commercial routers already spread traffic across providers by
default [@openrouter_exacto], so an auditor that flags mixed traffic will flag them too.

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
