# Sequential A/B testing with thin data: study design

Status: protocol text dated 2026-10-29. Results were generated on 2026-10-30; see section 13 for the run log, including post hoc analyses in 13.4. The sentence "The only code run so far is the dataset check in section 2" was wrong when first written and has been removed. [corrected 2026-10-30: the project is not a git repository and nothing has been committed. The protocol text is dated 2026-10-29. The choices in 13.1 are dated 2026-10-30, the day the grid ran. No timestamp in the project proves the order of protocol and results. That order is the author's statement only.]

Repository: `<repo>` (GitHub `jessieyang22/sequential-ab-testing-thin-data`, public). [updated 2026-10-31: published as a public repository on that date. The path above was the local folder at the time of writing.]

---

## 1. Research question

A small startup often has too little traffic to reach the sample size a standard test asks for. Which stopping rule should it use, and what does each rule cost?

Specifically, using real randomized data resampled to small per-arm sizes:

1. **Error rate.** When there is no real effect, how often does each rule declare a winner (false-positive rate, FPR)?
2. **Power.** When a real effect exists, how often does each rule detect it?
3. **Time to decision.** How many users does each rule need before it stops, and how often does it never stop?
4. **Agreement with the full-data answer.** When a rule stops, does its sign and size match the answer obtained from all the data?
5. **Peeking.** If a team checks the p-value after every batch of users and stops at the first p < 0.05, how far does the FPR rise above 0.05?

The rules compared are listed in section 5.

Two terms, defined literally:

- **Peeking** means checking the test result at several points while the test is running, and stopping the first time the p-value is below 0.05. A fixed-horizon test checks once, at the planned sample size.
- **Alpha spending** means dividing the total false-positive allowance (alpha = 0.05) across the planned looks, so each look may use only part of it. Group-sequential rules work this way. [wording corrected 2026-10-30: "budget" replaced by "allowance"; no change of meaning.]

Primary outcome: **conversion** (binary). Secondary outcome: **visit** (binary, about 4.7% base rate), which is closer to traffic levels of a typical product test. [corrected 2026-10-30: 4.7% is the pooled rate over the full file, (80,105 + 576,824) / 13,979,592 = 4.70%. The control rate is 3.82% and the treated rate is 4.85%.]

Primary estimand: **intention-to-treat (ITT)** difference in conversion rate between assigned treatment and assigned control. No other estimand is primary (see section 3.4).

---

## 2. Data

### 2.1 Dataset

- **Name:** Criteo Uplift Modeling Dataset, version 2.1 (research uplift v2.1).
- **Citation:** Diemert, E., Betlei, A., Renaudin, C., and Amini, M.-R. (2018). *A Large Scale Benchmark for Uplift Modeling.* AdKDD and TargetAd Workshop, KDD 2018.
- **Source URL:** https://huggingface.co/datasets/criteo/criteo-uplift
- **File:** `criteo-research-uplift-v2.1.csv.gz`
- **Direct download URL:** https://huggingface.co/datasets/criteo/criteo-uplift/resolve/main/criteo-research-uplift-v2.1.csv.gz
- **Size:** 311,422,618 bytes compressed (about 311 MB). Uncompressed: 3,248,115,221 bytes (measured 2026-10-29). Acquisition and profile are documented in `DATA.md`.
- **Rows:** 13,979,592 user rows (header not counted). Matches the dataset card.
- **Columns:** `f0` to `f11` (12 anonymized dense float features), `treatment` (1 = assigned to receive ads, 0 = held out), `conversion` (0/1), `visit` (0/1), `exposure` (0/1).
- **Design:** randomized incrementality tests. A random share of users is withheld from ads. The dataset card says it was assembled from several such tests and sub-sampled non-uniformly for privacy. The features were randomly projected and anonymized.

### 2.2 Verification done (2026-10-29)

Each item below was run in this session.

| Check | Result |
|---|---|
| Reachable (HTTP GET on the direct URL) | HTTP 200, `content-length` 311,422,618 |
| Partial read of first 3 MB of the gzip stream | Decodes to CSV; header matches the column list above |
| Full download to a scratch folder outside the repo | 311,422,618 bytes |
| `gzip -t` on the full file | Passes |
| Row count (data rows, header excluded) | 13,979,592. Matches the dataset card |
| SHA-256 of the full download | `2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc`. Matches the Hugging Face `x-linked-etag` |
| License on the dataset card | `cc-by-nc-sa-4.0` (see section 2.3) |

Large enough: yes. Per-arm sizes are shown in 2.4 and are far above the per-arm sizes in the design grid.

### 2.3 License and terms (what they allow)

License: **CC BY-NC-SA 4.0** (Creative Commons Attribution-NonCommercial-ShareAlike 4.0).

What this means for this repository:

- **Allowed:** using the data for research and a public, non-commercial portfolio project, with attribution (cite Diemert et al. 2018 and link the dataset page).
- **Not allowed:** any commercial use. This repository must stay non-commercial. **Jessie: this dataset cannot be used for ACT, Extendy, or any other commercial work, including code adapted from this repository.**
- **Share-alike:** if row-level data derived from the file is published, the derived data must carry the same license. For that reason this repository will **not commit any row-level data**, raw or resampled. Only aggregate numbers (FPR, power, mean time to decision, and similar) and figures built from them are committed.
- **Download script:** `data/download.sh` fetches the file from the URL above into `data/raw/` (git-ignored). It checks the SHA-256 before use. The raw file is never committed.

### 2.4 Full-data descriptive counts (computed 2026-10-29, before any method was run)

These counts were computed from the full file to confirm its structure. They are reported here so that the evaluation protocol below can be read against them. They were not used to choose the protocol, which was fixed in the sections that follow.

| Group | Users | Conversions | Conversion rate | Visit rate | Share with `exposure` = 1 |
|---|---|---|---|---|---|
| Control (`treatment` = 0) | 2,096,937 | 4,063 | 0.1938% | 3.82% | 0 (by construction) |
| Treated (`treatment` = 1) | 11,882,655 | 36,711 | 0.3089% | 4.85% | 3.60% |

Treated share: 85.0%.

Full-data ITT difference in conversion: **0.1152 percentage points** (relative lift about 59%). Normal-approximation 95% CI for the difference: [0.1085, 0.1219] points. This interval is not yet a validated result. It is the "full-data answer in this file," subject to the balance and SRM checks in section 4 (component C1). [corrected 2026-10-30: these counts come from the full file, which includes partition H. H supplies every reported number, so H is not a clean holdout for design inputs. The design inputs (base rate, lift, n) were chosen from these counts. The closed-form n from the H counts is 29,624 per arm. Results for the feature-adjusted estimate and its effect on n are in results/sensitivity_S5_design_inputs.json.]

Expected control conversions at 5,000 users per arm: about 9.7. This is the thin-data regime the study targets.

---

## 3. Evaluation protocol (fixed before any method comparison is run)

### 3.1 Random split

- Seed: **20261029**. Generate a random permutation of all 13,979,592 row indices with this seed (`numpy.random.default_rng(20261029).permutation`).
- **Development partition D:** first 20% of the permuted indices (2,795,918 rows). Used only for writing and debugging code, and for checking that the code runs. **No reported number comes from D.**
- **Held-out partition H:** remaining 80% (11,183,674 rows). Every reported number comes from H, except the validation check in 3.3, which uses both H and the full file.
- Splitting is by random permutation, not by file position. The first rows of the file are adjacent near-duplicates, so row order is structured.

### 3.2 Known-truth benchmarks

Two constructed scenarios have a truth that holds by construction. These are the **primary** benchmarks. The full-data ITT is a secondary reference.

**Scenario A (A/A, true effect = 0).** Both arms are drawn at random from H-control rows only. The two arms have the same real conversion distribution, so any rule that declares a winner is a false positive.

**Scenario M(p) (labelled mixture, true effect = p × pool difference).** The treatment arm for each draw is built row by row: with probability p the row is drawn from H-treated, otherwise from H-control. The control arm is drawn from H-control. The expected conversion rate of the treatment arm is then p·r_T + (1 − p)·r_C, where r_T and r_C are the conversion rates of H-treated and H-control. The true effect is exactly **p · (r_T − r_C)**, computed from the pool rates and not from any sample.

Values of p: **0.25, 0.5, 1.0**. Scenario A is the p = 0 case. At p = 1.0 the scenario reproduces the real ITT on H.

This mixture is a resampling of real rows. It is not synthetic data. It is labelled in every output file and in the write-up.

### 3.3 Validation against the full-data answer (decided now)

Before any result is generated, these checks are fixed. If a check fails, the failure is reported and the study stops at that point. No result is reported from a failed stage.

- **V1 (partition check).** The H-only ITT difference must lie inside the full-data 95% CI in 2.4. If it does not, H is not representative of the full file, and results from H are reported as H-specific only. [corrected 2026-10-30: V1 is a consistency check and not an independent validation. H is 80% of the full file, so its estimate lies inside the full-file interval largely by construction.]
- **V2 (engine check).** The fixed-horizon z-test run on Scenario A must return an FPR inside the band in section 7.
- **V3 (boundary check).** The group-sequential boundaries must match the reference package output (component C3).
- **V4 (always-valid check).** The mSPRT implementation must pass its own A/A FPR band (component C3).

### 3.4 Estimand, and why exposure is not primary

ITT is the primary estimand: the effect of being assigned to receive ads, in the same way a product test assigns users to a variant.

The `exposure` column is 0 in every control row by construction, so a complier-based or treatment-on-treated estimate is not cleanly identified from this file. Exposure-based estimates are not reported as results. They appear only as a descriptive note.

### 3.5 Design grid

| Factor | Levels |
|---|---|
| Scenario | A (p = 0), M(0.25), M(0.5), M(1.0) |
| Per-arm sample size n (users per arm) | 2,000; 5,000; 10,000; 25,000; 50,000 |
| Method | 6 methods in section 5 |
| Outcome | conversion (primary); visit (secondary, robustness R1) |
| Repetitions R | 2,000 per cell |
| Seed for resampling | 20261029 + cell index (recorded per cell) |

Primary grid: 4 × 5 × 6 × 2,000 = **240,000 simulated experiments**. [clarified 2026-10-30: these are rule-by-repetition evaluations. They come from 4 × 5 × 2,000 = 40,000 simulated paths, each of which is scored by all six rules.]

Look schedules (number of users per arm at each look):

- Naive peeking, Bayesian threshold rule, and mSPRT: a look every 500 users per arm, up to n. A run with n = 50,000 has 100 looks.
- Group-sequential O'Brien-Fleming and Pocock (Lan-DeMets alpha spending): **K = 5** equally spaced looks, at n/5 multiples.
- Fixed-horizon tests: one look, at n.

Alpha: **0.05**, two-sided, for every rule that targets 5% error. Bayesian rule: posterior probability of positive lift above **0.95**.

Priors for the Bayesian rule: Beta(1, 1) on each arm's conversion rate, independent.

Common random numbers: within each repetition, one set of resampled rows is drawn and passed to every method. This reduces the variance of method differences.

Stopping is evaluated at each scheduled look, in order. The first look where the rule declares a winner (in either direction) is the stop. If no rule fires by the last look, the run is **undecided**. No futility stopping is used.

---

## 4. Analysis components

There are **seven** distinct analysis components. Each is a separate code unit with its own check. Each component writes its output to `results/` as a CSV or Parquet file, plus a log line recording the seed.

**C1. Data pipeline and randomization checks.**
- Download (`data/download.sh`), checksum (SHA-256), load, split (3.1).
- Balance check on H, between treated and control: standardized mean difference (SMD) on each of `f0` to `f11`. Pre-set failure rule: any |SMD| > 0.1 is flagged. A flagged feature is reported, and the full-data ITT is labelled "the full-data answer in this file, not a causal effect" if more than 2 features are flagged.
- Sample ratio mismatch (SRM) check: chi-square goodness-of-fit of the treated share against 0.85, at p < 0.001. An SRM flag is reported and the ITT is treated as descriptive.
- Limit: the file has no test-ID column, so randomization is only guaranteed within each original test. The balance and SRM checks are the only way to see whether pooling broke it.

**C2. Power and sample-size calculator.**
- Closed-form sample size per arm for a two-proportion test at the real base rate (control 0.19%), for relative lifts of 15%, 30%, and 59%, at 80% power and alpha 0.05 (two-sided). Also computed for visit.
- Checked against simulated power from C4 at the fixed-horizon z-test. The calculator passes if simulated power is within 3 Monte Carlo SEs of 0.80 at the calculated n, for the Scenario M(1.0) case.

**C3. Stopping-rule implementations and validation.**
- (a) Fixed-horizon two-proportion z-test (normal approximation).
- (b) Fixed-horizon Fisher exact test. Included because the z-test is not reliable at about 10 expected conversions per arm.
- (c) Naive peeking: z-test at every 500-user look, stop at first p < 0.05.
- (d) Group-sequential, Lan-DeMets alpha spending, O'Brien-Fleming shape and Pocock shape, K = 5. **Boundaries are checked against R `gsDesign` or `rpact`** output for the same K and alpha, with tolerance 0.001 on the z-boundaries. The reference boundaries are generated by the package, not typed in from memory.
- (e) Always-valid mSPRT (Johari, Koomen, Pekelis, and Walsh; mixture sequential probability ratio test on the difference in proportions). **Validated by its own A/A run** at the 500-user schedule. Band in section 7.
- (f) Bayesian threshold rule (Beta-Binomial posterior, P(lift > 0) > 0.95), evaluated at every 500-user look.

Output of C3 is a function per rule that takes cumulative counts and returns stop / continue. Unit tests cover: boundary values against the reference package; the A/A FPR of each rule at n = 2,000 with R = 500 as a smoke test; and the rule returning "continue" when no data is given.

**C4. Resampling engine over real rows.**
- For each cell (scenario, n, outcome, repetition), draw rows from H with replacement across repetitions and without replacement within one repetition, using the recorded seed.
- Computes cumulative conversion counts at each look for both arms.
- Shares draws across methods (common random numbers).
- Scale: about 1.5 billion row draws in total across the primary grid (sum over n of 2n rows per repetition, times 4 scenarios, times 2,000 repetitions). The engine must be vectorized or compiled. A slow loop is not acceptable at this scale. [corrected 2026-10-30: the engine does not draw rows. It draws per-block conversion counts (blocks of 10 users per arm), vectorized over repetitions. The figure of 1.47 billion is the number of simulated users (2n per repetition, summed over the five n values, four scenarios and 2,000 repetitions). The count of block-level draws is about 73.6 million. Both figures are computed in results/sensitivity_S5_design_inputs.json. The primary grid took 271 seconds on the run machine.]
- Output per run: stopped (yes/no), look index at stop, users at stop, direction of the decision, estimated lift at stop.

**C5. Scoring against the known truth and the full-data answer.** For each method and cell:
- **FPR** (Scenario A): proportion of runs that declare a winner at any look.
- **Power** (Scenario M(p) with p > 0): proportion of runs that declare a winner in the correct direction.
- **Time to decision.** Two numbers, both reported:
  - mean users at stop, counting undecided runs at the maximum horizon (2 × n × number of looks at max);
  - median users at stop, for stopped runs only.
  - Also the **fraction undecided** at the maximum horizon.
- **Bias at stopping:** mean(estimated lift at stop) − true lift (from 3.2), for stopped runs. Reported in percentage points and as a ratio of true lift.
- **CI coverage at stop:** proportion of stopped runs whose 95% interval (for the rule's own estimator) contains the true lift. Reported for every rule that produces an interval (a, b, d, e). Rules (c) and (f) report posterior or Wald intervals at stop, labelled as such.
- **Agreement with the full-data answer:** for Scenario M(1.0), the proportion of stopped runs whose sign matches the full-data ITT sign, and the mean absolute difference between the stopped estimate and the full-data ITT.

**C6. Robustness checks.** Each is pre-specified. Results are reported whether or not they change the conclusions.
- **R1 (visit outcome).** Same grid, same methods, on the visit outcome (secondary, not primary).
- **R2 (1:1 allocation).** Treatment arm drawn from H-treated, subsampled to the control size, so the arms are balanced. Scenarios A and M(1.0) only, all methods, all n. Checks whether the 85/15 imbalance is driving any result.
- **R3 (schedule and alpha).** For the four sequential rules, two alternative schedules: (i) 100 looks at n/100 spacing for (c), (e), (f); (ii) alpha = 0.01. Checks whether the peeking and mSPRT results depend on the chosen look count.
- **R4 (covariate adjustment, sensitivity only).** Regression adjustment on `f0` to `f11` (CUPED-style) on the fixed-horizon z-test. The features are anonymized, and it is not known whether they are measured before treatment. This is labelled a sensitivity check and not a recommendation.

**C7. Figures.** Final figures are built in **R** (ggplot2), from CSVs in `results/`. Figures show: FPR by rule and n (Scenario A), power curves, time-to-decision with undecided fraction, bias at stop. Every figure is labelled with its scenario and the note "resampled real rows".

---

## 5. Methods (6 rules)

| ID | Rule | Looks | Stop criterion |
|---|---|---|---|
| M1 | Fixed-horizon z-test | 1 (at n) | p < 0.05, two-sided |
| M2 | Fixed-horizon Fisher exact test | 1 (at n) | p < 0.05, two-sided |
| M3 | Naive peeking z-test | every 500 users | first p < 0.05 |
| M4 | Group-sequential, O'Brien-Fleming shape | 5 | Lan-DeMets boundary crossed |
| M5 | mSPRT (always-valid) | every 500 users | mixture likelihood ratio > 1/alpha |
| M6 | Bayesian threshold | every 500 users | P(lift > 0) > 0.95 |

Pocock shape (K = 5) is run as a sensitivity variant of M4 in R3, not as a separate primary method. [note added 2026-10-30: M6 as specified uses thresholds 0.95 and 0.05. That is a two-sided error of 0.10 per look, not 0.05. A post hoc variant with thresholds 0.975 and 0.025 is in S4 (section 13.4).]

---

## 6. Pre-specified questions and what counts as an answer

- **Q1: Is the FPR of M3 (peeking) inflated above 0.05?** Supported if the Scenario A FPR of M3 at the 100-look schedule is at least 0.10, and its 95% Monte Carlo interval lies entirely above 0.07. Otherwise: "not supported in this grid," reported plainly.
- **Q2: Does M5 or M6 keep the FPR at or below 0.05 under peeking?** M5 is expected to, by construction. M6 has no such guarantee. Reported as measured. Supported claim: "M6 FPR was X at schedule Y." No claim beyond the grid.
- **Q3: Which method has the shortest time to decision at a fixed FPR?** Compared only among methods whose Scenario A FPR is inside the band in section 7. If none of the sequential methods beats M1 on time to decision at the same FPR, that result is reported as the answer.
- **Q4: Does the power of M1 at the calculated n (C2) match the simulated power?** Yes or no, within 3 Monte Carlo SEs.

Nothing in this list is answered by an un-run method, and no answer is reported from D.

---

## 7. Failure criteria and Monte Carlo bands

Monte Carlo SE of a rate near 0.05 at R = 2,000: sqrt(0.05 × 0.95 / 2,000) = 0.0049. Bands are set at about ±3 SE. [added 2026-10-30: the SE is largest at rates near 0.5. At 0.5 it is 0.0112. The Wilson 95% interval for each cell is in results/primary_grid.csv.]

| Check | Pass band | Action if it fails |
|---|---|---|
| V2: M1 FPR on Scenario A, n = 5,000 | [0.035, 0.065] | Engine is broken. Stop. Fix and rerun. Do not report any result from the engine. |
| V4: M5 FPR on Scenario A | ≤ 0.065 | mSPRT implementation is broken. Stop. Fix and rerun. [note added 2026-10-30: V4 is one-sided. A rule that never fires passes it. The check is therefore not evidence that M5 works. Separate evidence is in section 13.4 (S1 and R1).] |
| V1: H-only ITT inside full-data 95% CI | inside [0.1085, 0.1219] points | Report all results as H-specific. Do not describe them as full-data results. |
| V3: boundary values vs reference package | within 0.001 in z | Boundary code is broken. Stop. |
| C1 balance | no feature with \|SMD\| > 0.1 | Flag each feature. If more than 2 features are flagged, the ITT is labelled "the full-data answer in this file, not a causal effect." |
| C1 SRM | p ≥ 0.001 | Report ITT as descriptive only. |
| C2 power check | simulated power within 3 SE of 0.80 | Calculator is wrong. Fix before using it in the write-up. |

Method-level rule for calling a method "acceptable": FPR in Scenario A within [0.035, 0.065]. A method that fails this band is reported as **not controlling error at 0.05 in this grid**, not dropped from the table.

Null and negative results: reported as they are. This includes: a sequential rule that does not shorten time to decision; a rule whose FPR is inside the band but whose power is lower than M1; and a peeking inflation that is not supported under Q1.

---

## 8. Reporting rules

- Every number in the write-up is read from a file in `results/` that was written by a script in `src/`. No number is typed by hand.
- Each results file records: script name, git commit hash, seed, R, n grid, and date. [corrected 2026-10-30: no git commit hash exists, because the project is not a git repository (13.1.13). results/provenance.json records the other fields for every file.]
- The write-up (`README.md`) is written in plain English. Each step is explained in a short paragraph. No analogies or metaphors.
- A section titled **"What failed"** is kept in the README. It is not deleted when results look good. It lists failed checks (sections 3.3 and 7), changes to the design after the fact (with the reason and the date), and any result that was not reproduced on a second run. The same content is kept in section 13 of this file.

---

## 9. Limits

- **Data is not a startup's data.** Criteo is an advertising incrementality dataset from large-scale ad campaigns. Base rates and effect sizes are not typical of a small startup's product test. The results are about the statistical behavior of rules at these rates, not a claim about any company.
- **Subsampling by the source.** The file was sub-sampled non-uniformly. The full-data ITT is the answer in this file, not necessarily the population answer.
- **Pooled tests.** The file pools several incrementality tests with no test ID. Randomization is only guaranteed within each test. The balance and SRM checks (C1) are the only protection, and they are limited.
- **Anonymized, projected features.** Any covariate adjustment (R4) is a sensitivity check only.
- **One dataset.** Results are for this dataset at these base rates. They are not general.
- **Binary outcomes only.** Continuous metrics (revenue, time on site) are not covered here.
- **Monte Carlo error.** With R = 2,000, differences smaller than about 0.01 in FPR or power are not resolved.
- **Non-commercial license.** See section 2.3. No commercial use of this data or of code adapted to it.

---

## 10. Why this is hard to reproduce in a day

[corrected 2026-10-30: the paragraphs below overstated the work, and the review of 2026-10-30 found it. The corrected statement is this. The primary grid is 240,000 rule evaluations on 40,000 simulated paths, over a 311 MB compressed file of 13,979,592 rows. The engine draws conversion counts per block of 10 users, not rows. It ran in 271 seconds. The rules evaluated about 4.4 million looks for M3, M5 and M6 on the primary outcome (computed in results/sensitivity_S5_design_inputs.json). The protocol still needed seven components, a held-out partition, validation against gsDesign, robustness checks, and a section on failures. The original paragraphs follow for the record.]

The primary grid is 240,000 simulated experiments on a 311 MB compressed file with 13,979,592 rows. Three of the six rules check their stop decision at up to 100 looks per run. That is about **4.6 million look evaluations** for the primary outcome alone, before the robustness grid (roughly another 800,000 experiments in total).

The resampling engine has to draw about **1.5 billion rows** across the primary grid (2n rows per repetition, summed over five sample sizes, four scenarios, and 2,000 repetitions). The draws are shared across methods, and the code must be vectorized or compiled to finish in a reasonable time. Getting the draws, the cumulative counts, and the stop logic right at that scale takes repeated debugging.

Validation is a separate job from the simulation. The Lan-DeMets boundaries must be checked against an external package. The mSPRT must pass its own A/A band. The held-out partition must pass its check against the full-data interval. Each of those checks can fail, and a failure stops the study until it is fixed. The seven components each have their own output, check, and plain-English explanation, and the write-up has to explain every step to a reader without a coding background. Getting the protocol fixed before the results, keeping the held-out and development partitions separate, and writing an honest "what failed" section each take real time on top of the code.

---

## 11. Repository layout

```
sequential-ab-testing-thin-data/
  DESIGN.md              this file (protocol, fixed before the comparison runs)
  README.md              write-up (question, data, method, results, limits, what failed)
  data/
    download.sh          fetches the Criteo file into data/raw/ and checks SHA-256
    raw/                 git-ignored; the raw file is never committed
  src/
    c1_pipeline.py       download check, split, balance, SRM
    c2_power.py          closed-form sample size
    c3_rules.py          stopping rules
    c3_validate_R.R      boundary check against gsDesign or rpact
    c4_engine.py         resampling engine (real rows)
    c5_score.py          FPR, power, time to decision, bias, coverage
    c6_robustness.py     R1 to R4
  results/               CSV summaries only; no row-level data
  figures/               built in R (C7)
```

Language: Python for the engine and the rules (numpy, scipy). R for the boundary validation (`gsDesign` or `rpact`) and for the final figures (ggplot2).

---

## 12. Commit and sign-off

- [updated 2026-10-31: the first commit was made at publication, and the project is now a git repository. The protocol order is still the author's statement only, because the earliest git history is the publication commit.]
- No commit has been made at the time of writing. A local commit of this file is the timestamp that shows the protocol came before any result. Commit only when Jessie asks.
- Nothing is pushed. Pushing is a separate request.
- Any future commit message in this repository ends with the attribution line from the harness reminder, not from the workflow text.

---

## 13. Failures and null results

Entries are dated. Items in 13.1 are readings or implementation choices made before the primary grid was run, where the design text left a gap. None of them changes a pre-specified number. Items in 13.2 are failures and corrections during the run. Items in 13.3 are results that did not come out as hoped.

### 13.1 Readings and choices made before the grid (2026-10-30)

1. **Engine (C4).** Stopping rules use only the conversion (or visit) count per arm. The engine draws each block's count from the hypergeometric distribution of the real held-out pools, which is the distribution of the count under sampling real rows without replacement. Equivalence was checked against direct row draws on the development partition D (6,000 repetitions, `results/debug/engine_check_D.json`). This is debugging only and no number from D is reported.
2. **Simulation step.** Paths are simulated in blocks of 10 users per arm. All look schedules are multiples of 10.
3. **mSPRT mixing variance.** The design did not give tau squared. Chosen rule: tau2 = 2 r_C (1 - r_C) / n, where r_C is the H control rate and n is the planned per-arm size. Fixed per cell and the same at every look. This choice makes M5 very conservative (see 13.3).
4. **Bayesian rule (M6).** P(lift > 0) is computed exactly with the beta-binomial identity P(pC < pT) = P(BetaBinomial(nC + 1, aT, bT) >= aC), with aC = xC + 1, bC = nC - xC + 1 (and the same for T). Checked against Monte Carlo (10^6 draws) in `src/c3_unit_tests.py`. Negative direction: P(lift > 0) < 0.05.
5. **Intervals at stop.** Every rule uses the Wald interval for the difference in proportions, at 95%. This is not adjusted for sequential looks. Coverage is therefore reported as a naive quantity for M3 to M6. Fisher's (M2) interval is also Wald.
6. **Undecided runs.** Counted as 2n total users (n per arm). The wording "2 x n x number of looks at max" does not parse, so it was read this way.
7. **Q1.** The 100-look schedule is R3(i) (look every n/100 users). It is evaluated at each n. The headline is n = 50,000, where the 100-look schedule and the primary 500-user schedule coincide.
8. **V4.** Read as: M5's Scenario A false-positive rate is at most 0.065 at every n.
9. **R2 not run.** The R2 text draws the treated arm from H-treated under Scenario A, which creates a real effect and conflicts with Scenario A. The primary grid already uses equal arm sizes, so the 85/15 split does not enter any primary result. R2 is recorded as not run.
10. **Band rule.** The band [0.035, 0.065] is two-sided. A conservative method (for example M2, or M5 at small n) lands below the band. It is reported as outside the band, which the rule says, but it is not inflated.
11. **R4.** Row-level draws for Scenarios A, M(0.5) and M(1.0), at all n, R = 2,000. Features are standardized on the control rows of H. Labelled sensitivity only.
12. **C2 cell.** Reserved cell index 60 (seed 20261089).
13. **Git.** [updated 2026-10-31: the project was published to GitHub on 2026-10-31. Git history starts at that commit. The text below describes the state before publication.] The project directory is not a git repository. Nothing has been committed or pushed. A commit has not been made, so the protocol has no timestamp that proves it came before the results. [added 2026-10-30: the 2026-10-29 protocol text and the 2026-10-30 choices in 13.1 cannot be separated by any record in the project. Ordering is the author's statement, not evidence. A git repository and a commit are unresolved. Committing now would not prove the protocol came first.]

### 13.2 Failures and corrections during the run (2026-10-30)

1. **V3 first run failed.** The Python Lan-DeMets OBF spending used the two-sided z (1.96) where the one-sided form needs z = qnorm(1 - a/4). A first bisection direction error was also present. Both were fixed. The second run gave a maximum difference of 0.00068 on the z scale against gsDesign 3.11.0 (tolerance 0.001, pass). The gsDesign values were not changed. (`results/v3_boundary_check.json`)
2. **Engine debug check at 500 repetitions** showed a treated-arm variance gap of about 2.4 Monte Carlo SE against direct row draws. At 6,000 repetitions the KS p-values were 0.996 (control) and 0.706 (treated) (`results/debug/engine_check_D.json`). The 500-repetition result was noise, not an engine error.
3. **Slow Beta-binomial tail.** The scipy `betabinom.sf` call sums over the whole support for each element. The first visit-outcome run (R1) stalled for more than 15 minutes at n = 10,000 and was stopped. Its output was not used. The tail was replaced with an exact tail sum over the shorter tail, checked against scipy to about 2e-10 on valid inputs. The primary grid was rerun with the new code and reproduced every number of the earlier run exactly. The R1, R3, R4 and answer scripts were then rerun.
4. **Test inputs.** Two unit-test inputs were invalid (conversions larger than users). They were corrected. No rule output came from invalid inputs.
5. **R4 sampler.** The first R4 attempt used numpy's without-replacement `choice`, which permutes the full 1.68 million-row pool on every repetition. It did not finish in several minutes and was stopped before any output was written. It was replaced by a sampler that draws with replacement and keeps the first distinct values, which is a uniform sample without replacement. The R4 output comes only from the replacement sampler.
6. **R4 undefined z.** When a sampled arm has no conversions, the HC1 variance is zero and the regression z is undefined. Such repetitions count as no reject, and the count is written to `results/robust_R4_cuped.csv` (`undefined_z_count`).
7. **Chain interruption.** A shell step that stopped a running job also stopped the chain that was waiting to run the answers script. The answers script was then run directly with the same code. No result was affected.
8. **Provenance added after the run (metadata only, no rerun).** Section 8 asks every results file to record its script, git note, seed, R, n grid and date. Several files did not. `src/c9_provenance.py` writes `results/provenance.json` with those fields for every results file. Its dates are file modification times, not times written by the producing scripts. No number changed. The file is `src/c9_provenance.py`, run on 2026-10-30.

### 13.3 Results that did not come out as hoped

These are results, not failures of the code. Full tables are in `results/`.

- **M5 (mSPRT) has very low power under the chosen mixing variance.** It rarely declares a winner at n up to 25,000 even when the true effect is the full observed lift. The mixing variance was chosen by rule (13.1.3), not tuned to the data. A different mixing variance could change this. A post hoc sensitivity analysis (section 13.4) explored it.
- **Peeking inflates the false-positive rate.** Under Scenario A, M3 and M6 exceed 0.05 by a wide margin at every n in the primary grid (see `results/answers.json`, Q1 and Q2).
- **Sequential rules did not clearly shorten time to decision at the same false-positive rate.** [corrected 2026-10-30, wording made consistent with README section 6.6 (Q3): among the rules inside the band at a given n, M4 has the shortest mean time. The saving against M1 is small at n = 2,000 (about 1%) and large at n = 50,000 in Scenario M(1.0) (about 31%: 69,120 against 100,000 users). Only M1 and M4 are inside the band at n up to 10,000, and M2 joins at n of 25,000 and above. The answer therefore compares two rules at small n. It does not establish a general ranking. The figures are in results/answers.json, field Q3_time_to_decision.]
- **R4 regression adjustment did not improve power.** Under Scenario M(1.0) the adjusted test had lower power than the unadjusted test at n of 5,000 and above (for example 0.168 against 0.202 at n = 5,000, counted in the correct direction). A post hoc diagnostic (section 13.4) found the adjusted estimate slightly less variable but shifted down under Scenario M(1.0), so R4 is not a recommendation (`results/robust_R4_cuped.csv`).
- **Bias at stop is large at small n.** For stopped runs at n = 2,000 the estimated lift is several times the true lift for every rule. This is the winner's curse for runs that stop early.

### 13.4 Post hoc sensitivity analyses (added 2026-10-30, after the primary grid and R1 to R4 were run)

Not in the protocol. Decided after the primary results were seen, so they do not change any pre-specified answer. Code: `src/c10_sensitivity.py`. Outputs: `results/sensitivity_S1_M5_tau2.csv`, `results/sensitivity_S2_R4_diagnostic_M1.0_n50000.json`, `results/sensitivity_S2_R4_diagnostic_A_n50000.json`. Provenance added to `results/provenance.json`.

1. **S1 (M5 mixing variance).** The mixing variance was multiplied by 0.1, 1, 10 and 100, on the same simulated paths as the primary grid. Multiplier 1 reproduces the primary M5 numbers exactly. Scenario A rates stay at or below 0.0145 at every n for all four multipliers. Scenario M(1.0) power at n = 50,000 is 0.0000 (0.1), 0.4410 (1), 0.8130 (10) and 0.7650 (100). M5's low power in section 6.2 therefore depends on the variance choice. No multiplier was selected as a default.
2. **S2 (R4 diagnostic, 500 repetitions, n = 50,000).** Under Scenario M(1.0) the adjusted estimate has a standard deviation 0.92 times the unadjusted one, and its reported standard error is 0.93 times the unadjusted one, so the lower power is not from extra variance or an inflated standard error. The adjusted estimate averages 0.000978 against a true effect of 0.001153 (unadjusted average 0.001173). Under Scenario A the adjusted estimate averages -0.0000139 (unadjusted -0.0000151). The same shift appears on the full held-out pool with no resampling (S3: feature-adjusted treatment coefficient 0.0924 points against 0.1153 unadjusted; `results/sensitivity_S3_full_H_ols.json`). This is consistent with small feature differences between the treated and control pools that predict conversion. The data do not separate that from differences in the effect across users.
3. **S3 (full-pool check).** Feature-adjusted regression on all rows of H, with no resampling. The shift is -0.0229 points. It is reported as a diagnostic only.
4. **Data-source labels (implementation note).** Section 3.2 says the simulated label appears in every output file. In practice the label is recorded in `results/provenance.json` (field `data_source`), in the S1 and S2 outputs, and on every figure. The existing CSV files were not rewritten, so they do not carry the label in their own columns. [updated 2026-10-30: the primary grid, R1, R3, R4 and every S file now carry a `data_source` column, written by the scripts and not by hand. The grid was rerun, and its numbers were checked against the earlier run.]

### 13.5 Review and correction round (2026-10-30, after the first write-up)

An outside review of the write-up found issues. The fixes are listed here, and the code that does each fix is named. None of them changes a pre-specified answer. Each is dated. Numbers were regenerated by code in `src/` and the write-up was updated to match.

1. **Post hoc S4 (M6 thresholds matched to a two-sided 0.05 per look).** Rule M6 as pre-specified stops at P(lift > 0) > 0.95 or < 0.05. That is a two-sided error of 0.10 per look. S4 reruns M6 at 0.975 and 0.025 on the same cell paths. Results: `results/sensitivity_S4_M6_matched_alpha.csv`.
2. **Post hoc S5 (design inputs and descriptive numbers).** Closed-form n at the feature-adjusted effect, the 85:15 allocation factor, the |z| that the mSPRT rule needs at its planned n, Monte Carlo resolution, and the simulation workload. Results: `results/sensitivity_S5_design_inputs.json`.
3. **Post hoc S6 (alternative truth).** Scenario M(p) with p chosen so that the true effect equals the feature-adjusted full-pool estimate from S3. All primary rules are rerun on new paths, so power, time, bias and coverage can be read against that truth. Results: `results/sensitivity_S6_alternative_truth.csv`.
4. **Provenance.** `src/c9_provenance.py` now refuses to run if a results file has no producer. It records "not applicable" for simulation fields in files that use no simulation. It was run last, because it records file times.
5. **Logs.** The console logs in `results/debug/` are now written by the commands in README section 3, with output redirected to the named file.
6. **Reproducibility pins.** `requirements.txt` pins numpy 2.0.2, scipy 1.13.1 and pandas 2.3.3. R versions are in README section 3.
7. **Figures.** The rules use a colour-blind-safe palette with distinct shapes. Figures 3 and 4 leave out cells with fewer than 50 stopped runs.
8. **R assertion.** `src/c3_validate_R.R` now asserts that the null crossing totals equal the two-sided alpha to within 1e-6. Before this change it only printed them.
9. **Labels only.** "budget" was replaced by "allowance" in the README and in DESIGN section 1. The engine docstring says "pool" where it said "urn". No result changed.

