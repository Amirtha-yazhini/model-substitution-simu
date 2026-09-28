# Paper plan: COMSNETS 2027 CSP Workshop

**Venue:** Cyber Security and Privacy Workshop (CSP), COMSNETS 2027, Bengaluru, January 2027.
<https://www.comsnets.org/cybersecurity_and_privacy_workshop>

| Requirement | Value |
|---|---|
| Length | **6 pages**, IEEE two-column format, references and figures included |
| Review | **Double-blind** |
| Submission | PDF through **EDAS** |
| Presentation | One author registers and presents **in person** |
| Proceedings | IEEE Xplore |
| Deadline | *To be announced* (checked 2026-09-24). Past years: mid-to-late October. **Recheck weekly.** |

**Topics to claim:** *AI and ML security and privacy* and *Authentication, authorization, and
accounting*. Frame model substitution as an **accounting-integrity** failure at an **untrusted
network intermediary**, with GATEOPS as a **timing side channel**.

---

## How we work

- **You** write each section in plain Markdown in `drafts/NN_*.md`. Rough is fine.
- **Claude** turns it into `sections/NN_*.tex`, compiles, checks every number against
  `results/paper_numbers.md`, and reports the page count.
- Numbers are copied from result files, never retyped from memory.

**Conventions for drafts** (so the conversion is mechanical):

| You write | Becomes |
|---|---|
| `[@bruckner2025]` | `\cite{bruckner2025}` |
| `(Fig. F2)` / `(Tab. arms)` | `Fig.~\ref{fig:F2}` / `Table~\ref{tab:arms}` |
| `$\epsilon^*$` | inline math, unchanged |
| Markdown pipe table | `booktabs` table |
| `**A5**` | `\textbf{A5}` |
| `> NOTE: ...` | a note to Claude, not converted |

**Build:** `python paper/build.py`. This compiles `main.pdf`, prints the page count, and warns
if it is over 6 pages.

---

## Page budget

| # | Section | Budget | Draft file |
|---|---|---|---|
| 0 | Abstract | ~150 words | `drafts/00_abstract.md` |
| 1 | Introduction and threat model | 0.75 pp | `drafts/01_introduction.md` |
| 2 | Related work | 0.5 pp | `drafts/02_related.md` |
| 3 | System design: SHIM, ARENA, sealed protocol | 1.0 pp | `drafts/03_design.md` |
| 4 | Results: coverage, grid, live run | 1.75 pp | `drafts/04_results.md` |
| 5 | Economics and the confound | 1.0 pp | `drafts/05_economics.md` |
| 6 | Checks added after sealing (exploratory) | 0.75 pp | `drafts/06_posthoc.md` |
| 7 | Limitations and conclusion | 0.5 pp | `drafts/07_conclusion.md` |
| | References | 0.5 pp | `refs.bib` |
| | **Total** | **6.0 pp** | |

---

## Phase 0: Setup (Claude) ✅
- [x] `paper/` with IEEEtran conference template, anonymous mode
- [x] Section stubs in `sections/` and draft stubs in `drafts/`
- [x] Empty `refs.bib`
- [x] `build.py`: compile and count pages (uses Tectonic in `paper/.tools/`, not committed)

Setup notes:
- Tectonic fetches packages from a server that sometimes times out. If a build fails with
  "failure fetching", run it again; downloaded files are cached.
- The bibliography lines in `main.tex` are commented out until `refs.bib` has its first entry,
  because an empty bibliography does not compile.
- If Tectonic cannot reach its package server, install TeX Live (`texlive-latex-extra`,
  `texlive-publishers`, `latexmk`) and run `PAPER_LATEX=latexmk python paper/build.py`.
- `main.tex` also compiles unchanged on Overleaf (pdfLaTeX): upload `main.tex`, `sections/`,
  `refs.bib` and `figures/`.

## Phase 1: Fix the evidence (Claude, 2–4 days, $0) ✅
Done before any prose, so the text never has to be rewritten because a number changed.
- [x] **Protocol v2:** fix the `>=` tie rule (use `>`) and the calibration on coarse
      statistics. Re-seal with a new SHA-256 and tag `frozen-v2`. Re-run the grid, holdout and
      eps sweep. v1 stays untouched and is reported as sealed.
- [x] **Fit the mock to measurement:** fit latency and number preferences to the census and
      live data. Re-run the eps sweep. This answers "the personalities are hand-written."
- [x] **Confidence intervals:** more mock seeds, Wilson intervals on power and false-positive
      rates, bootstrap interval on eps\*.
- [x] **Paper figures:** single column, readable in grayscale, saved as PDF in `paper/figures/`.
- [ ] ~~*(Optional)* A small live A5 (probe-aware evasion) run on Groq, if quota allows.~~ Skipped: A5 routes by request shape, so live it would only confirm the classifier matches its own probes.
- [x] **Output:** `results/paper_numbers.md`, one sheet with every number the paper cites.

Phase 1 notes:
- v2 SHA-256 `534a56f2…`, tag `frozen-v2`. An earlier v2 seal (`8a395d7d`) was replaced before any
  evaluation ran, because its input hash depended on line endings. The thresholds were identical.
- The v1 "discreteness" explanation was wrong: v1's GATEOPS threshold was an unlucky draw.
- **eps\* = 0.10 on both ladders, but IRIS-lite sets it, and on the real census text IRIS-lite
  cannot separate 20b from 120b.** Post-hoc, without IRIS-lite: 0.10 (hand-written mock) and
  0.15 (fitted mock). Claim a range, not a single value.
- OTE on the fitted mock barely detects dilution (0% at eps = 0.10), because the real 120b and 20b
  share their top three answers. It still separates full substitution (AUROC 1.00).
- Figures: `fig_power`, `fig_break_even`, `fig_coverage`, `fig_evasion`, `fig_fpr`,
  `fig_confound`, `fig_live` (PDF, fonts embedded as TrueType).

## Phase 2: Structure (you, 1 day)
Before writing any prose, write in `drafts/01_introduction.md`:
- [ ] Working title
- [ ] 3–4 contribution bullets, one sentence each
- [ ] The one-sentence finding a reviewer should remember

Claude checks each claim against the evidence so the paper never claims more than the results
support.

**Findings that do not depend on the mock** (lead with these):
1. Probe-aware evasion (A5) beats all six auditors, because of how probes are shaped.
2. Real-endpoint coverage: RUT runs on 0/11, and OTE as published on 4/11.
3. Real-response OTE: 20b vs 120b separated at p = 4.5e-6. `system_fingerprint` rotates on
   honest traffic.
4. Live Groq run: the real latency gap is 18%, not 3×. A9's latency shaping backfires.
5. The identity / disclosure / billing taxonomy from the A3-vs-A11 confound.

## Phase 3: Core sections (you write, Claude converts; about 1 week)
Easiest first. After each one, Claude converts, compiles and reports pages remaining.
- [ ] 3a. **System design** (1.0 pp). Source: REPORT §2. Arms table.
- [ ] 3b. **Results** (1.75 pp). Source: REPORT §3, v2 numbers with intervals. Figures F3, F4 and
      the live-run table.
- [ ] 3c. **Economics and confound** (1.0 pp). Source: REPORT §4–5. Figures F2 and F6.

## Phase 4: Framing sections (you write, Claude converts; 3–4 days)
- [ ] 4a. **Related work** (0.5 pp). Give Claude the 8 detector papers (titles or arXiv links).
      Claude builds `refs.bib` and checks each entry exists.
- [ ] 4b. **Introduction and threat model** (0.75 pp). Accounting integrity at an untrusted
      gateway. Ends with the Phase 2 contribution bullets.
- [ ] 4c. **Limitations and conclusion** (0.5 pp). The 4–5 limitations from REPORT §6 that
      matter most.
- [ ] 4d. **Abstract** (~150 words). Written last.

## Phase 5: Fit and polish (together, 2–3 days)
- [x] Cut to 6 pages (6/6, figures regenerated at column width with 7.5–8 pt fonts, all fonts embedded).
- [x] Consistency pass: every number in the PDF checked against `results/` (paper numbers and the
      post-hoc tables in `results/v2/tables/`).
- [ ] Anonymisation:
  - [x] No names or emails in any tracked file; no API keys; no personal paths. Names appear only in
        git commit history, which Anonymous GitHub does not mirror.
  - [x] PDF metadata stripped (`main.tex`: empty hyperref fields, `\pdfsuppressptexinfo=-1`,
        `\pdfinfoomitdate=1`, `\pdftrailerid{}`); `pdfinfo` shows no author, creator, producer or dates.
  - [ ] **You:** create the anonymised link (steps below) and send it; Claude replaces the
        placeholder in `sections/07_conclusion.tex`.
  - [x] No self-citations.
- [x] Read-through as a reviewer: five mock reviews (`REVIEW_skeptical*.md`), each with outcomes.

**Creating the anonymised repository link** (needs your GitHub login, so Claude cannot do it):
1. Go to <https://anonymous.4open.science> and sign in with GitHub.
2. Choose "Anonymize a repository" and paste `https://github.com/Amirtha-yazhini/model-substitution-simu`.
3. Branch: the one you submit from (after merging the paper PR, `main`).
4. Terms to anonymize (one per line): `Amirtha-yazhini`, `Amirtha`, `Yazhini`, `amirthayazhini`.
5. Turn off the link to the original repository; set expiry after the conference (January 2027).
6. Copy the resulting `https://anonymous.4open.science/r/<id>/` link and send it to Claude.

## Phase 6: Submit (you)
- [ ] Create an EDAS account and register the paper early (some workshops need the title and
      abstract first).
- [ ] Run the PDF through IEEE PDF eXpress if required.
- [ ] Upload. Prepare the artifact repo for camera-ready.

---

**Timeline:** about 3.5 weeks. If the announced deadline is earlier, drop the optional live A5
run and the mock fitting first.
