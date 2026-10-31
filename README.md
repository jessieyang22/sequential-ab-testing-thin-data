# Sequential A/B testing with thin data

This repository asks one practical question: a small team with little traffic wants to check an A/B test before the planned sample size is reached. Which stopping rule should it use, and what does each rule cost in false winners, missed effects and time?

The answers come from simulations. Each simulated test draws users from one public randomized dataset (the Criteo uplift file, section 2). The draws are real users with real outcomes, and the simulation resamples them into small test arms. The stopping rules see only the number of conversions in each arm at each check. Row order, the anonymized features, the time of the test, and which original test a user came from are not used. So the method assumes that users are independent and that conversion happens at a constant rate. It has no time trends, no novelty effects and no structure within a test. Section 8 lists these limits.

Every number below was produced by code in `src/` and is stored in `results/`. The protocol text is in `DESIGN.md`, dated 2026-10-29. The data facts are in `DATA.md`.

Status: the full pipeline has been run on the held-out partition H. After an outside review on 2026-10-30, the write-up was corrected, several results were regenerated, and three post hoc analyses were added (section 6.9). Every correction is listed in section 7. The project was published as a public GitHub repository on 2026-10-31. Git history starts at that publication commit. The order in which the protocol and the results were written is the author's statement only and is not verified (section 7, item 21; section 9).

---

## Terms used in this write-up

Each term is explained once, in plain words.

- **Arm.** One group of users in a test. The control arm gets no ads. The treated arm gets ads.
- **Conversion rate.** The share of users in an arm who convert.
- **Lift, or ITT difference.** The treated conversion rate minus the control conversion rate. The file gives a difference of 0.1153 percentage points on H. "Intention-to-treat" (ITT) means users are compared by the group they were assigned to, whether or not they saw an ad.
- **False-positive rate (FPR).** The share of tests with no real effect in which a rule still declares a winner.
- **Power.** The share of tests with a real effect in which a rule declares a winner in the correct direction.
- **Fixed-horizon test.** One check, at the planned sample size.
- **Peeking.** Checking the result many times during a test and stopping the first time the p-value is below 0.05.
- **p-value.** The probability of a difference at least as large as the observed one if there were no real effect.
- **z-test.** A standard test that compares two rates using a normal approximation. The "pooled" version uses one variance estimate for both arms, as if there were no effect.
- **Fisher exact test.** A test that computes the p-value from exact probabilities, so it does not depend on the normal approximation. It is conservative (it declares a winner less often than 5% of the time) when conversions are few.
- **Alpha spending.** Dividing the 5% false-positive allowance across the planned checks, so that each check may use only part of it.
- **Group-sequential test (Lan-DeMets alpha spending).** A test with a fixed, small number of planned checks, where the allowance is spent by a formula (Lan and DeMets).
- **O'Brien-Fleming shape and Pocock shape.** Two spending formulas. O'Brien-Fleming spends very little at early checks and most at the end. Pocock spends about the same at each check.
- **gsDesign.** An R package that computes group-sequential boundaries. It is used here as the reference for the boundaries.
- **mSPRT (mixture sequential probability ratio test).** A rule that compares a likelihood ratio, averaged over possible effect sizes, with a threshold of 1/alpha. It is designed so that its error rate holds at every check ("always-valid"). Here the variance is estimated from the data at each check, so the guarantee is approximate, not exact.
- **Bayesian threshold (M6).** The rule stops when the posterior probability that the treated rate is higher is above 0.95, or below 0.05. The posterior probability is the probability of the effect given the data, under a prior.
- **Beta(1,1) prior.** A flat prior over all conversion rates between 0 and 1.
- **Beta-binomial distribution.** The distribution of conversion counts when the underlying rate has a Beta distribution. It is used to compute M6's probability exactly.
- **Hypergeometric distribution.** The distribution of the number of converters in a sample drawn without replacement from a pool with a known number of users and converters. The simulation engine uses it to draw conversion counts.
- **Wald interval.** The estimate plus or minus 1.96 standard errors. The standard error is the estimated spread of the estimate.
- **HC1 robust standard errors.** Standard errors for a regression that stay valid when the spread of the outcome differs between groups.
- **Regression adjustment (CUPED style).** Using a regression on pre-test features to reduce the noise in the comparison. CUPED is the name of one such method, used in `DESIGN.md`.
- **Kolmogorov-Smirnov (KS) test.** A test of whether two samples come from the same distribution. It is used in the engine check.
- **Standardized mean difference (SMD).** The difference between two group means divided by a pooled standard deviation. An SMD above 0.1 in size is flagged as imbalance.
- **Sample ratio mismatch (SRM).** The treated share of users differs from the designed share, which would suggest that assignment was not random as designed.
- **Monte Carlo error.** The random error caused by using a finite number of simulated repetitions. With 2,000 repetitions, a rate of 0.05 has a standard error of 0.005.
- **Wilson interval.** A 95% interval for a rate that behaves well when the rate is near 0 or 1. The Monte Carlo intervals in the results use it.
- **Undecided.** A run in which a rule never stopped by its last check.
- **Bias at stop.** The average distance between the lift estimated at the stopping point and the true lift, for runs that stopped.
- **Coverage.** The share of 95% intervals, built at the stopping point, that contain the true lift.
- **Unadjusted and feature-adjusted.** The unadjusted estimate is the plain difference in conversion rates. The feature-adjusted estimate comes from a regression that includes the twelve anonymized features.

---

## 1. Question

Using simulations that resample real rows from the held-out partition, to small per-arm sizes:

1. **Error rate.** When the true effect is zero, how often does each rule declare a winner? This is the false-positive rate (FPR).
2. **Power.** When a real effect exists, how often does each rule find it in the right direction?
3. **Time to decision.** How many users does each rule need before it stops, and how often does it never stop?
4. **Agreement with the full-data answer.** When a rule stops, does its sign and size match the answer from all the data?
5. **Peeking.** If a team checks the p-value after every batch of users and stops at the first p < 0.05, how far does the FPR rise above 0.05?

Six stopping rules are compared (section 4.3).

Two terms as used here:

- **Peeking** means checking the test result several times while it runs, and stopping the first time the p-value is below 0.05.
- **Alpha spending** means dividing the 5% false-positive error allowance across the planned checks, so that each check may use only part of it.

---

## 2. Data

- **Dataset.** Criteo Uplift Modeling Dataset, version 2.1 (Diemert, Betlei, Renaudin and Amini, 2018, AdKDD and TargetAd workshop at KDD 2018). Source: https://huggingface.co/datasets/criteo/criteo-uplift
- **What it is.** About 14.0 million users from randomized advertising incrementality tests. A random share of users was withheld from ads. Each row has twelve anonymized features (`f0` to `f11`), the assignment (`treatment`), and outcome flags (`conversion`, `visit`, `exposure`).
- **Pooled tests.** The file pools several tests and has no test ID. Randomization is only guaranteed inside each original test. Section 8 discusses what this means for the results.
- **Size.** The file is 311 MB compressed. It is not committed. `data/download.sh` fetches it into `data/raw/` (git-ignored) and checks the SHA-256 hash before use.
- **Base rates.** Conversion is about 0.19% in the control arm and 0.31% in the treated arm (full file). Visit is 3.82% in control and 4.85% in treated. The pooled visit rate over the full file is 4.70%.
- **Dates.** The file has no timestamp, so the study cannot say when the tests ran.
- **Licence.** CC BY-NC-SA 4.0. Non-commercial use only, with attribution, and share-alike. No row-level data derived from the file is committed. Only aggregate results and figures are in this repository.

### Split

- A fixed random permutation (seed 20261029) splits the rows into a development partition D (20%, 2,795,918 rows) and a held-out partition H (80%, 11,183,674 rows).
- D was used only for writing and debugging code. No reported number comes from D.
- Every reported number comes from H, except the V1 consistency check (section 5), which compares H with the full file.

### Limits of H as a holdout for design decisions

H is 80% of the full file. The design inputs (the control base rate of 0.19%, the lift of 59%, and the sample size of 29,630 per arm) were chosen from counts on the full file, and those counts include H. So H is not a clean holdout for design decisions. The closed-form sample size from H alone is 29,624 per arm. A design based on the feature-adjusted estimate would need about 44,050 per arm (section 6.9, S5).

---

## 3. What is in the repository

```
DESIGN.md              the protocol (text dated 2026-10-29), plus dated corrections and logged changes in sections 13 and 13.5
DATA.md                what the raw file contains (observed facts only)
README.md              this write-up
data/download.sh       fetches the Criteo file into data/raw/ and checks its SHA-256
src/common.py          shared constants and helpers
src/data_profile.py    profile of the raw file (counts, ranges, missingness)
src/c1_pipeline.py     C1: split, balance check, sample ratio check, V1 consistency check, aggregate pools
src/c2_power.py        C2: closed-form sample size and a simulated power check
src/c3_rules.py        C3: the stopping rules
src/c3_boundaries.py   C3: group-sequential boundaries computed in Python (checked against R)
src/c3_validate_R.R    C3: reference boundaries from the R package gsDesign, with an assertion
src/c3_unit_tests.py   unit tests for the rules and the engine
src/c4_engine.py       C4: resampling engine over the real held-out rows
src/c5_score.py        C5: runs the primary grid and scores every rule against the known truth
src/c6_robustness.py   C6: R1 (visit outcome), R3 (schedules and alpha), R4 (covariate sensitivity)
src/c10_sensitivity.py post hoc sensitivity analyses S1 to S6 (section 6.9)
src/c8_answers.py      answers to the pre-specified questions Q1 to Q4
src/c9_provenance.py   provenance record for every results file (file producer, simulation or not, seed, R, n grid)
figures/make_figures.R C7: figures in R (ggplot2), built from the CSV files in results/
results/               CSV and JSON summaries, and console logs in results/debug/. No row-level data.
```

To reproduce, from the repository root (the redirects write the console logs named in `results/provenance.json`):

```
pip install -r requirements.txt
./data/download.sh
python3 src/data_profile.py
python3 src/c1_pipeline.py
Rscript src/c3_validate_R.R > results/debug/c3_validate_R.log 2>&1
python3 src/c3_boundaries.py > results/debug/v3_run.log 2>&1
python3 src/c3_unit_tests.py > results/debug/c3_unit_tests.log 2>&1
python3 src/c4_engine.py
python3 src/c5_score.py > results/debug/c5_run.log 2>&1
python3 src/c6_robustness.py R1 > results/debug/c6_R1.log 2>&1
python3 src/c6_robustness.py R3 > results/debug/c6_R3.log 2>&1
python3 src/c6_robustness.py R4 > results/debug/c6_R4.log 2>&1
python3 src/c10_sensitivity.py all > results/debug/c10_sensitivity.log 2>&1
python3 src/c2_power.py
python3 src/c8_answers.py > results/debug/c8.log 2>&1
Rscript figures/make_figures.R
python3 src/c9_provenance.py
```

Versions used. Python 3.9.6 with numpy 2.0.2, scipy 1.13.1 and pandas 2.3.3 (pinned in `requirements.txt`). R 4.6.1 with gsDesign 3.11.0 (boundaries), and for the figures ggplot2 4.0.3, dplyr 1.2.1 and scales 1.4.0. Exact reproduction of the simulated numbers depends on these versions. NumPy does not promise that random draws stay identical across releases.

Run times on the machine used (8 CPU cores, 8 GB RAM, other programs running). The primary grid took 298 seconds, R3 146 seconds, the full sensitivity script 96 seconds when run alone, R1 718 seconds, and R4 2,474 seconds. R1 and R4 ran alongside other jobs while the machine was swapping, and the sensitivity script was stopped once for that reason and restarted alone. The timings depend on load. The numbers did not change between runs.

**Fresh re-run on 2026-10-31.** The project was copied without `results/` and `data/raw/` to a new folder. The Criteo file was downloaded with `data/download.sh` (36 seconds, SHA-256 and size verified), and every step in the list above was run in order on one machine with no other heavy jobs. The whole pipeline took about 20 minutes (R1 147 seconds, R3 56, R4 706, the sensitivity script 118, the primary grid 53). The timings are not results. Every CSV in `results/` and `answers.json` was reproduced byte for byte. The JSON files differ only in their run timestamps and in `provenance.json` file times. The debug logs differ only in their timing lines. The figures were regenerated but were not compared pixel for pixel. The numbers in sections 6.1, 6.7 and 6.9 were checked against the CSV and JSON files, and no change was needed. The `git` fields in `results/provenance.json` describe the state before publication, when the project was not a git repository.

---

## 4. Method, step by step

Each step below is written for a reader with no coding background. The file names show where the code lives.

### 4.1 Split and checks (C1, `src/c1_pipeline.py`)

1. The raw file is read once and each column is saved as a compact binary array in `data/raw/cache/`. Those arrays are git-ignored.
2. All row numbers are shuffled with the fixed seed. The first 20% are set aside as D and the rest are H.
3. **Balance check.** For each feature, the difference between treated and control users on H is measured as a standardized mean difference (SMD). A feature is flagged if |SMD| > 0.1. No feature is flagged.
4. **Sample ratio check.** The treated share on H is compared with the design share of 0.85 using a chi-square test. A mismatch would suggest the assignment was broken. There is none (p = 0.813 on H).
5. **V1 consistency check.** The H-only difference in conversion rates must fall inside the 95% interval computed from the full file. It does. This check is a consistency check only. H is 80% of the full file, so H's estimate lies inside the full-file interval largely by construction. It is not an independent validation.

### 4.2 Simulated experiments (C4, `src/c4_engine.py`)

A simulated experiment has a control arm and a treatment arm, each with n users. Users are resampled from the real held-out rows:

- **Scenario A (no effect).** Both arms are drawn from H-control. Any winner is a false positive.
- **Scenario M(p) (a known fraction of the H difference).** Each treated-arm user comes from H-treated with probability p, and otherwise from H-control. The true effect is exactly p times the difference between the H-treated and H-control conversion rates, computed from the pool rates and not from any simulated sample. For p = 1.0 this is the full unadjusted H difference, 0.1153 percentage points.

Within one repetition, no user is drawn twice. The rules need only the number of conversions per arm at each check. The engine therefore draws the number of conversions in each block of 10 users from the exact hypergeometric distribution of the real pool. This is the distribution that drawing real rows without replacement would give, so it is a computational shortcut and not synthetic data. The engine does not draw rows.

The engine check (`results/debug/engine_check_D.json`) compares this shortcut with direct draws of real rows. It covers one sample size (n = 2,000), one p (0.5), final counts only, and the development partition D. The Kolmogorov-Smirnov tests found no difference between the two methods (p = 0.996 for control counts, 0.706 for treated counts). The check does not cover intermediate counts or other sample sizes.

All six rules in one repetition look at the same simulated arms (common random numbers). Differences between rules are therefore not caused by different random draws.

### 4.3 Stopping rules (C3, `src/c3_rules.py`)

| Rule | What it does | When it looks | Two-sided error per look |
|---|---|---|---|
| M1 | Fixed-horizon z-test, pooled variance, two-sided p < 0.05 | Once, at n | 0.05 |
| M2 | Fixed-horizon Fisher exact test, two-sided p < 0.05 | Once, at n | 0.05 (exact test, conservative) |
| M3 | Naive peeking: z-test, stop at the first p < 0.05 | Every 500 users per arm | 0.05 at each look |
| M4 | Group-sequential, Lan-DeMets alpha spending with the O'Brien-Fleming shape | Five equal looks | 0.05 in total |
| M5 | mSPRT, a mixture likelihood ratio above 1/alpha, with the variance estimated at each look | Every 500 users per arm | 0.05 (approximate) |
| M6 | Bayesian threshold: stop when P(lift > 0) > 0.95 or < 0.05, with Beta(1,1) priors | Every 500 users per arm | **0.10** (0.05 in each direction) |

Notes that matter for reading the results:

- When there are no conversions at all in a look, the z-test gives no reject, and the rule is said to continue.
- **M6 is not at the same error level as the others.** Its thresholds 0.95 and 0.05 leave 0.05 in each tail, so a single look declares a winner by chance about 0.10 of the time. The other rules are at 0.05 two-sided. The primary grid therefore compares M6 at a doubled error level. A post hoc variant with thresholds 0.975 and 0.025 (two-sided 0.05 per look) is reported in section 6.9 (S4). It is labelled post hoc and does not replace M6.
- The Bayesian probability P(lift > 0) is computed exactly, not by sampling, using an identity for Beta distributions (checked against Monte Carlo in `src/c3_unit_tests.py`).
- **The mSPRT mixing variance (M5) was fixed by a rule before the grid was run** (`DESIGN.md` section 13.1.3). That rule sets the mixing variance equal to the variance of the difference at the planned sample size. At the planned sample size (the last look), the rule declares a winner only when the z-value is about 3.66 or more (section 6.9, S5). A fixed test needs 1.96. Earlier looks need a larger z-value still. This is why M5 is very conservative and has low power in the primary grid. The result is a property of this threshold, not evidence about mSPRT in general. Section 6.9 (S1) shows how power changes with the mixing variance.
- **M5 is "always-valid" only approximately.** The rule estimates the variance of the difference from the data at each look (a plug-in estimate). The error guarantee of the mSPRT method holds exactly only when the variance is known. Here it is estimated, so the guarantee is approximate.

### 4.4 Group-sequential boundaries (C3, V3)

The M4 boundaries come from the R package gsDesign (version 3.11.0). `src/c3_validate_R.R` generates them and asserts that the null crossing probabilities add up to the two-sided alpha (0.05 and 0.01) to within 1e-6. `src/c3_boundaries.py` computes the same boundaries independently in Python. The check V3 passes if they agree within 0.001 on the z scale. The M4 boundaries used in scoring come from gsDesign.

### 4.5 Scoring (C5, `src/c5_score.py`)

For each cell (scenario, n, rule), over 2,000 repetitions:

- FPR in Scenario A, with a 95% Wilson interval for the Monte Carlo error.
- Power in Scenario M(p) (declared winner in the correct direction).
- Undecided share (no stop by the last look).
- Time to decision: mean total users over all runs (undecided runs count as 2n), and the median among stopped runs.
- Number of stopped runs (`n_stopped`).
- Bias at stop: mean estimated lift at stop minus the true lift, for stopped runs.
- Coverage at stop: share of stopped runs whose 95% Wald interval contains the true lift.
- Agreement with the full-data answer in Scenario M(1.0): share of stopped runs whose sign is positive, and the mean absolute gap to the full-data estimate.

**Thin cells.** Any statistic computed only among stopped runs (bias, coverage, sign agreement, median users at stop) is reported as "not estimable" when fewer than 50 runs stopped. The threshold of 50 is set here, after the review. Such cells are marked "n/e" in the tables. The numbers are still in `results/primary_grid.csv`.

### 4.6 Power calculator (C2, `src/c2_power.py`)

The closed-form sample size is computed for two-proportion tests at the H control rate, with alpha 0.05 (two-sided) and power 0.80. A simulated check then runs M1 at the calculated n. The check passes if the simulated power is within three Monte Carlo standard errors of 0.80.

### 4.7 Robustness checks (C6, `src/c6_robustness.py`)

- **R1.** The full grid on the visit outcome (a secondary outcome with a 3.8% control base rate).
- **R2.** Not run. See `DESIGN.md` section 13.1.9.
- **R3.** (i) 100 looks at n/100 spacing for M3, M5 and M6. (ii) alpha = 0.01 for M3, M4, M5 and M6. (iii) Pocock spending as a variant of M4. These use the same simulated paths as the primary grid.
- **R4 (sensitivity only).** Regression adjustment on the twelve features, with robust (HC1) standard errors, compared with the unadjusted test on the same real rows. The features are anonymized and it is not known whether they were measured before treatment. The adjusted and unadjusted estimates answer different questions when effects vary across users or the adjustment model is wrong (section 6.7). So R4 is not a recommendation.
- **Post hoc analyses S1 to S6.** Section 6.9.

### 4.8 Pre-specified questions (`src/c8_answers.py`)

- **Q1.** Is the FPR of M3 (peeking) inflated above 0.05? Supported if the FPR at the 100-look schedule is at least 0.10 and the 95% Monte Carlo interval lies entirely above 0.07. Read at n = 50,000.
- **Q2.** Does M5 or M6 keep the FPR at or below 0.05 under peeking?
- **Q3.** Which method has the shortest time to decision at a fixed FPR? Compared only among methods whose Scenario A FPR is inside the band in section 5.
- **Q4.** Does the power of M1 at the calculated n match the simulation?

---

## 5. Validation checks

Each check was decided before the results were generated. The thresholds are in `DESIGN.md` section 7.

| Check | What it tests | Value from the run | Pass rule | Result |
|---|---|---|---|---|
| V1 (consistency) | H-only ITT difference (conversion) lies inside the full-file 95% interval. Not independent: H is part of the full file. | H-only ITT 0.1153 points; full-file interval [0.1085, 0.1219] | inside the interval | Pass |
| C1 balance | Any feature with \|SMD\| above 0.1 between treated and control on H | 0 of 12 features flagged; largest \|SMD\| 0.049 (f3) | none flagged | Pass |
| C1 sample ratio | Treated share against the design share 0.85 | full file p = 0.999; H p = 0.813 | p at least 0.001 | Pass |
| V2 | M1 false-positive rate, Scenario A, n = 5,000 | simulated 0.049; exact (binomial sum) 0.0513 | inside [0.035, 0.065] | Pass |
| V3 | Python Lan-DeMets boundaries against gsDesign 3.11.0 (20 boundaries: 4 sets of 5) | largest difference 0.00068 on the z scale (rerun 2026-10-30) | below 0.001 | Pass |
| V4 (one-sided) | M5 false-positive rate, Scenario A, every n | 0 at n = 2,000 to 10,000; 0.0010 at n = 25,000; 0.0005 at n = 50,000 | at most 0.065 | Pass. **This check is one-sided.** A rule that never declares a winner passes it. It is not evidence that M5 works. Evidence on M5 power is in R1 and S1. |
| C2 | M1 simulated power in Scenario M(1.0) at n = 29,630 (closed-form n 29,624.1, rounded up to 29,625; the simulation uses the next multiple of the 10-user block) | 0.7975 | 0.773 to 0.827 (80% plus or minus 3 Monte Carlo SE) | Pass |
| Engine check | Count engine against drawing real rows (development partition D, debugging only) | control KS p = 0.996; treated KS p = 0.706 (6,000 repetitions, n = 2,000, p = 0.5) | distributions agree | Pass for that setting only |
| Unit tests | Beta-binomial probability against Monte Carlo; fast tail sum against scipy; zero-data behaviour | all pass (rerun 2026-10-30) | see `results/debug/unit_tests.txt` | Pass |

The engine check and unit tests are debugging evidence. Neither is a reported result.

---

## 6. Results

All numbers in this section come from `results/primary_grid.csv` (conversion outcome, 2,000 repetitions per cell), unless a different file is named. The grid was rerun on 2026-10-30 and reproduced every number of the earlier run exactly. Each cell uses the real held-out rows. The true effect in Scenario M(1.0) is the **unadjusted** full held-out ITT difference, 0.1153 points (absolute), which is a relative lift of about 59%. Scenario M(0.5) and M(0.25) have half and a quarter of that effect. Section 6.9 (S3 and S6) shows what changes if the truth is the feature-adjusted estimate, 0.0924 points.

### 6.1 False-positive rate when there is no effect (Scenario A)

Share of runs that declared a winner at any look. The design band is 0.035 to 0.065.

The Monte Carlo standard error of each rate is sqrt(p(1 − p) / 2,000). It is 0.005 for rates near 0.05, and it is 0.011 for rates near 0.36 to 0.51, such as M3 and M6 at n = 50,000. The 95% Wilson interval for each cell is in the columns `fired_ci_lo` and `fired_ci_hi` of `results/primary_grid.csv`. Some intervals are quoted in the text.

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M1 fixed z | 0.0455 | 0.0490 | 0.0460 | 0.0490 | 0.0515 |
| M2 fixed Fisher | 0.0215 | 0.0285 | 0.0325 | 0.0400 | 0.0405 |
| M3 peeking z | 0.1070 | 0.1610 | 0.2270 | 0.2970 | 0.3595 |
| M4 group-seq OBF | 0.0405 | 0.0515 | 0.0490 | 0.0520 | 0.0465 |
| M5 mSPRT | 0.0000 | 0.0000 | 0.0000 | 0.0010 | 0.0005 |
| M6 Bayesian threshold (two-sided 0.10 per look) | 0.1380 | 0.2335 | 0.3465 | 0.4665 | 0.5140 |

Reading the table:
- M1 (fixed z) is inside the band at every n. M4 (group-sequential) is inside the band at every n.
- M2 (Fisher) is below the band at n = 2,000 to 10,000. It is conservative (it rarely declares a winner by chance), and this is a result, not an error. The band rule is two-sided and classifies it as outside.
- M3 (peeking) and M6 (Bayesian threshold) are far above 0.05, and the excess grows with n. More looks give more chances to cross the threshold by chance. M6 also has a doubled error per look (section 4.3). Section 6.9 (S4) separates these two causes.
- M5 (mSPRT) almost never declares a winner. It is within the upper limit, but at this mixing variance it is very conservative.

### 6.2 Power: share of runs that declared the correct winner

Scenario M(1.0), where the true effect equals the unadjusted held-out ITT difference:

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M1 fixed z | 0.1045 | 0.2110 | 0.3745 | 0.7480 | 0.9550 |
| M2 fixed Fisher | 0.0650 | 0.1520 | 0.3310 | 0.7190 | 0.9495 |
| M3 peeking z | 0.1585 | 0.3400 | 0.5455 | 0.8615 | 0.9645 |
| M4 group-seq OBF | 0.1060 | 0.2070 | 0.3670 | 0.7375 | 0.9535 |
| M5 mSPRT (see caveat) | 0.0000 | 0.0015 | 0.0085 | 0.1110 | 0.4410 |
| M6 Bayesian threshold | 0.2070 | 0.4580 | 0.6735 | 0.9110 | 0.9645 |

**Caveat for M5.** Its low power comes from the mixing variance fixed by the rule in section 4.3. At the planned sample size the rule needs a z-value of about 3.66 to declare a winner, against 1.96 for a fixed test, and earlier looks need more (section 6.9, S5). Section 6.9 (S1) shows that a larger mixing variance gives much higher power and the same low false-positive rate. Its power here should not be read as the power of mSPRT in general.

Power of M3 and M6 cannot be read on its own. Both have high false-positive rates (section 6.1), so part of their power is the same false-positive mechanism. For example, at n = 25,000 M6 has power 0.9110 and a false-positive rate of 0.4665. Under the doubled per-look error of M6, that power is partly chance. Section 6.9 (S4) gives the matched-error variant.

**Dependence on the truth.** The power figures above assume the unadjusted truth, 0.1153 points. If the truth is the feature-adjusted estimate, 0.0924 points (S3), power is lower. Section 6.9 (S6) gives the full table. For example, M1 has power 0.5635 at n = 25,000 and 0.8595 at n = 50,000, against 0.7480 and 0.9550 above.

### 6.3 Time to decision

Mean total users (both arms) over all runs in Scenario M(1.0). Runs that never stopped count as 2n. Fixed-horizon rules always use 2n.

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M1 fixed z | 4,000 | 10,000 | 20,000 | 50,000 | 100,000 |
| M2 fixed Fisher | 4,000 | 10,000 | 20,000 | 50,000 | 100,000 |
| M3 peeking z | 3,742 | 8,236 | 13,694 | 21,428 | 25,911 |
| M4 group-seq OBF | 3,954 | 9,735 | 18,838 | 41,795 | 69,120 |
| M5 mSPRT | 4,000 | 9,999 | 19,974 | 49,081 | 90,650 |
| M6 Bayesian threshold | 3,682 | 7,559 | 11,758 | 16,312 | 19,311 |

Share of runs that never stopped (undecided) in Scenario M(1.0):

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M1 fixed z | 0.8885 | 0.7870 | 0.6250 | 0.2520 | 0.0450 |
| M2 fixed Fisher | 0.9310 | 0.8475 | 0.6690 | 0.2810 | 0.0505 |
| M3 peeking z | 0.8240 | 0.6430 | 0.4375 | 0.1210 | 0.0175 |
| M4 group-seq OBF | 0.8880 | 0.7905 | 0.6325 | 0.2625 | 0.0465 |
| M5 mSPRT | 1.0000 | 0.9985 | 0.9915 | 0.8890 | 0.5590 |
| M6 Bayesian threshold | 0.7705 | 0.5145 | 0.2980 | 0.0630 | 0.0055 |

Number of stopped runs out of 2,000 in Scenario M(1.0). Any statistic among stopped runs is "n/e" when this count is below 50 (section 4.5):

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M1 fixed z | 223 | 426 | 750 | 1,496 | 1,910 |
| M2 fixed Fisher | 138 | 305 | 662 | 1,438 | 1,899 |
| M3 peeking z | 352 | 714 | 1,125 | 1,758 | 1,965 |
| M4 group-seq OBF | 224 | 419 | 735 | 1,475 | 1,907 |
| M5 mSPRT | 0 | 3 | 17 | 222 | 882 |
| M6 Bayesian threshold | 459 | 971 | 1,404 | 1,874 | 1,989 |

**Allocation.** The grid uses equal arms (1:1). The source data were split 85:15. For the same variance, a 85:15 design needs about 1.96 times as many users in total as a 1:1 design (1/0.85 + 1/0.15, divided by 4; `results/sensitivity_S5_design_inputs.json`). The time totals in this section are therefore totals for a 1:1 design. They are not totals for an 85:15 design.

### 6.4 Bias and interval coverage at the stop

Relative bias = (mean estimated lift at the stop minus the true lift) divided by the true lift, for stopped runs. A value of 0 means unbiased. "n/e" means fewer than 50 runs stopped (section 4.5).

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M1 fixed z | 2.05 | 1.12 | 0.61 | 0.18 | 0.03 |
| M2 fixed Fisher | 2.41 | 1.30 | 0.67 | 0.19 | 0.03 |
| M3 peeking z | 2.49 | 1.91 | 1.40 | 0.88 | 0.69 |
| M4 group-seq OBF | 2.37 | 1.37 | 0.81 | 0.31 | 0.11 |
| M5 mSPRT | n/e (0 stops) | n/e (3 stops) | n/e (17 stops) | 0.82 | 0.34 |
| M6 Bayesian threshold | 2.28 | 1.60 | 1.19 | 0.86 | 0.71 |

Coverage: share of stopped runs whose 95% Wald interval contains the true lift, in Scenario M(1.0). The Wald interval is not adjusted for repeated looks, so coverage for M3 to M6 is a naive quantity.

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M1 fixed z | 0.6906 | 0.8967 | 0.9507 | 0.9679 | 0.9728 |
| M2 fixed Fisher | 0.5435 | 0.8656 | 0.9456 | 0.9666 | 0.9726 |
| M3 peeking z | 0.7557 | 0.9020 | 0.9351 | 0.9556 | 0.9628 |
| M4 group-seq OBF | 0.7277 | 0.8401 | 0.9279 | 0.9471 | 0.9764 |
| M5 mSPRT | n/e | n/e (3 stops) | n/e (17 stops) | 0.6577 | 0.9127 |
| M6 Bayesian threshold | 0.8039 | 0.9094 | 0.9352 | 0.9525 | 0.9517 |

In Scenario A, the 95% intervals of M1 to M4 exclude zero in every stopped run, so their coverage is 0 at every n. For M1, M3 and M4 this follows from the test itself. With equal arm sizes, the pooled standard error used by the z-test is at least the unpooled Wald standard error used for the interval. The pooled variance uses the average rate, and because p(1 − p) is concave, its value at the average rate is at least the average of its values at the two rates. So when the pooled z-statistic passes its critical value, the Wald interval must exclude zero. The boundaries of M4 are all above 1.96 (`results/gsdesign_boundaries.csv`), so the same holds at every look. For M2 (Fisher's test) the zero coverage is an observed result. Scenario A coverage is therefore **not informative** for M1 to M4, and it is not shown as a result.

**The truth matters here too.** These coverage and bias figures are measured against the unadjusted truth. Section 6.9 (S6) gives them against the feature-adjusted truth.

### 6.5 Agreement with the full-data answer

Share of stopped runs whose estimated sign is positive (the full-data ITT sign is positive), Scenario M(1.0). "n/e" means fewer than 50 runs stopped.

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M1 fixed z | 0.9372 | 0.9906 | 0.9987 | 1.0000 | 1.0000 |
| M2 fixed Fisher | 0.9420 | 0.9967 | 1.0000 | 1.0000 | 1.0000 |
| M3 peeking z | 0.9006 | 0.9524 | 0.9698 | 0.9801 | 0.9817 |
| M4 group-seq OBF | 0.9464 | 0.9881 | 0.9986 | 1.0000 | 1.0000 |
| M5 mSPRT | n/e | n/e (3 stops) | n/e (17 stops) | 1.0000 | 1.0000 |
| M6 Bayesian threshold | 0.9020 | 0.9434 | 0.9594 | 0.9723 | 0.9698 |

### 6.6 Answers to the pre-specified questions (`results/answers.json`)

**Q1. Is the false-positive rate of M3 (peeking) inflated above 0.05?** Yes, supported at every n. Using the 100-look schedule (R3(i)), the Scenario A rate is 0.1440 at n = 2,000 (95% Monte Carlo interval 0.1293 to 0.1601), 0.2115 at 5,000 (0.1942 to 0.2299), 0.2745 at 10,000 (0.2554 to 0.2945), 0.3200 at 25,000 (0.2999 to 0.3408), and 0.3595 at 50,000 (0.3388 to 0.3808). The headline value at n = 50,000 is 0.3595.

**Q2. Does M5 or M6 keep the false-positive rate at or below 0.05 under peeking?**

- M5 does: its rate is 0.0000 to 0.0010 on the primary schedule and on the 100-look schedule, at every n. Its power is very low, as section 6.2 shows (with the caveat given there).
- M6 does not. Its rate is 0.1380 to 0.5140 on the primary schedule, and 0.1810 to 0.5140 on the 100-look schedule. These are the thresholds as pre-specified (two-sided 0.10 per look).
- Post hoc (S4). With thresholds matched to a two-sided 0.05 per look (0.975 and 0.025), M6's Scenario A rate is 0.0595 at n = 2,000, 0.1265 at 5,000, 0.1885 at 10,000, 0.2735 at 25,000, and 0.3340 at 50,000 on the 500-user schedule. At 100 looks and n = 50,000 the rate is 0.3340 (95% interval 0.3137 to 0.3550). M3 at 100 looks is 0.3595 (Q1). So the matched M6 still keeps the rate far above 0.05. Matching the threshold removes part of the excess, not all of it.
- The primary M6 result (0.5140) is therefore partly a threshold effect and partly peeking. The claim that Bayesian peeking is worse than classical peeking is **not** supported by this grid. At matched error, M6 and M3 are close to each other at n = 50,000 (0.3340 against 0.3595, with overlapping intervals).

**Q3. Which method has the shortest time to decision at a fixed false-positive rate?** Only methods whose Scenario A rate is inside the band 0.035 to 0.065 are compared. These are:

- at n = 2,000 to 10,000: M1 and M4 only;
- at n = 25,000 and 50,000: M1, M2 and M4.

Among these, M4 has the shortest mean time at every n. In Scenario M(1.0), the mean total users for M4 against M1 are 3,954 against 4,000 at n = 2,000 (a saving of 1.2%), 9,735 against 10,000 at n = 5,000 (2.7%), 18,838 against 20,000 at n = 10,000 (5.8%), 41,795 against 50,000 at n = 25,000 (16.4%), and 69,120 against 100,000 at n = 50,000 (30.9%). M4's share of undecided runs is close to M1's (0.0465 against 0.0450 at n = 50,000), and its power is close to M1's (0.9535 against 0.9550 at n = 50,000). Scenario A gives almost no difference between them.

The answer is therefore a comparison of two rules (M1 and M4) at small n. The saving grows with n and with the true effect, and it is not a general ranking. M3 and M6 have shorter mean times in Scenario M(1.0), but they are outside the band in Scenario A, so the rule excludes them. M5 has the longest mean time because it rarely stops. The comparison does not recalibrate each rule's threshold to a common false-positive rate. That would be needed to make a fair time comparison across all six rules, and it was not done (section 9).

**Q4. Does the power of M1 at the calculated n match the simulation?** Yes, for the unadjusted truth. The closed-form n is 29,624.1 per arm (rounded up to 29,625) for the observed 59.5% relative lift. The simulation ran at 29,630, the next multiple of the 10-user block. The simulated power at that n is 0.7975, inside the band 0.773 to 0.827 (`results/c2_power_check.json`). For the feature-adjusted truth (0.0924 points), the closed-form n is about 44,050 per arm (S5), and M1 has power 0.5635 at n = 25,000 and 0.8595 at n = 50,000 (S6). The calculator answers the question it was given, and the answer depends on the truth.

### 6.7 Robustness checks

**R1 (visit outcome, secondary).** Scenario A false-positive rates, `results/robust_R1_visit_grid.csv`:

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M1 fixed z | 0.0555 | 0.0585 | 0.0480 | 0.0540 | 0.0495 |
| M2 fixed Fisher | 0.0415 | 0.0555 | 0.0455 | 0.0525 | 0.0490 |
| M3 peeking z | 0.1235 | 0.1980 | 0.2465 | 0.3280 | 0.3765 |
| M4 group-seq OBF | 0.0545 | 0.0600 | 0.0470 | 0.0570 | 0.0500 |
| M5 mSPRT | 0.0000 | 0.0005 | 0.0005 | 0.0000 | 0.0000 |
| M6 Bayesian threshold | 0.2300 | 0.3510 | 0.4225 | 0.5420 | 0.5760 |

The visit outcome gives the same ranking as conversion: M3 and M6 inflate, M1, M2 and M4 are close to 0.05, and M5 is near zero.

The visit effect is larger (27% relative lift at a 3.8% base rate). This gives a check that M5 is not an "always-continue" rule. Its power in Scenario M(1.0) on the visit outcome is 0.0185 at n = 2,000, 0.1085 at 5,000, 0.4500 at 10,000, 0.9805 at 25,000 and 1.0000 at 50,000. At n = 25,000, M1 and M4 have power 1.000 on this outcome. The visit result is secondary, and it is a sanity check on the rule, not a replacement for the conversion result.

**R3 (schedule and alpha), `results/robust_R3_schedule_alpha.csv`.** Scenario A false-positive rates:

| Variant | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M3, 100 looks | 0.1440 | 0.2115 | 0.2745 | 0.3200 | 0.3595 |
| M6, 100 looks (two-sided 0.10 per look) | 0.1810 | 0.2980 | 0.4105 | 0.4945 | 0.5140 |
| M5, 100 looks | 0.0000 | 0.0000 | 0.0000 | 0.0010 | 0.0005 |
| M3, alpha 0.01 | 0.0090 | 0.0285 | 0.0420 | 0.0670 | 0.0960 |
| M4, alpha 0.01 | 0.0065 | 0.0120 | 0.0080 | 0.0120 | 0.0110 |
| M5, alpha 0.01 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| M6, alpha 0.01 (thresholds 0.99 and 0.01) | 0.0180 | 0.0535 | 0.0850 | 0.1255 | 0.1560 |
| M4 with Pocock shape | 0.0185 | 0.0390 | 0.0445 | 0.0450 | 0.0470 |

Cutting alpha to 0.01 reduces but does not remove the peeking inflation for M3 and M6. At n = 50,000, M3 at alpha 0.01 is still 0.096. Power falls with alpha 0.01: at n = 50,000 in Scenario M(1.0), M4 with alpha 0.01 has power 0.8595, against 0.9535 at alpha 0.05. The Pocock variant of M4 has a rate of 0.0445 to 0.047 at n of 10,000 and above. At n = 2,000 it is 0.0185, so it is conservative there. M5 at alpha 0.01 has a rate of 0 at every n.

**R2 (allocation).** Not run. The design text for R2 cannot be applied as written, because drawing the treated arm from the treated pool under Scenario A would create a real effect. See `DESIGN.md` section 13.1. The allocation issue is discussed in section 6.3.

**R4 (covariate sensitivity, sensitivity only).** Regression adjustment on the twelve features (linear model with robust HC1 standard errors) compared with the unadjusted pooled z-test on the same real rows, 2,000 repetitions per cell (`results/robust_R4_cuped.csv`):

- Scenario A (no effect): the two-sided rejection rate is 0.0455 to 0.0505 unadjusted and 0.0465 to 0.0540 adjusted, across all n.
- Scenario M(1.0), power (rejection in the correct direction): 0.0935 unadjusted against 0.0925 adjusted at n = 2,000; 0.2020 against 0.1680 at n = 5,000; 0.9535 against 0.9040 at n = 50,000.
- Scenario M(0.5), power: 0.0470 unadjusted against 0.0550 adjusted at n = 2,000. Under Scenario A the adjusted test also rejects more at that n (two-sided 0.0540 against 0.0455), so this small gap is not a power gain. At n of 5,000 and above the adjusted test has lower power (0.0910 against 0.0790 at 5,000; 0.4915 against 0.4230 at 50,000).

**Why R4 is not like-for-like.** The adjusted and unadjusted tests do not target the same quantity when the effect differs across users, or when the adjustment model is wrong. R4 scores both against the same truth, the unadjusted 0.1153 points. So the "lower power of adjustment" in R4 is scored against a truth that the adjusted estimator does not target. It is not a like-for-like finding, and it does not show that adjustment reduces power in general.

The post hoc diagnostic S2 (section 6.9) at Scenario M(1.0), n = 50,000, over 500 repetitions, shows that the adjusted estimate is slightly less variable than the unadjusted one (ratio of standard deviations 0.92) and that its reported standard error is slightly smaller (ratio 0.93). The lower power therefore does not come from extra variance. The adjusted estimate averages 0.000978 against a true effect of 0.001153, while the unadjusted estimate averages 0.001173. Under Scenario A the adjusted estimate averages -0.000014 and the unadjusted -0.000015, so no shift appeared without a real effect. The full-pool regression (S3) gives the feature-adjusted estimate 0.0924 points on all of H, against 0.1153 unadjusted. So adjustment moves the estimate on the whole held-out pool as well.

The data do not show why. The shift could come from small feature differences between treated and control pools that predict conversion, or from differences in the effect across users, or from model error. The features are anonymized, so their predictive value and their timing relative to treatment were not examined. R4 is a sensitivity check only. It does not support using these features for adjustment. The undefined-z count (no conversions in a sampled arm) was 0 in every cell.

### 6.8 Figures

Built in R (ggplot2) from the CSV files, each labelled "resampled real rows". Colours are the Okabe-Ito colour-blind-safe set, and each rule has its own plotting shape.

- `figures/fig1_false_positive_rate.png`: Scenario A false-positive rate by rule and n, with the band and 95% Monte Carlo bars.
- `figures/fig2_power.png`: power by rule, n and effect fraction (unadjusted truth).
- `figures/fig3_time_to_decision.png`: median total users among stopped runs, Scenario M(1.0). Points with fewer than 50 stops are left out.
- `figures/fig4_bias_at_stop.png`: relative bias at stop, Scenario M(1.0). Points with fewer than 50 stops are left out.

### 6.9 Post hoc sensitivity analyses

These analyses were added on 2026-10-30, after the primary results and the robustness checks were seen. They were not in `DESIGN.md` before the run, so they cannot change any pre-specified answer. They are labelled as post hoc in every output file. The code is `src/c10_sensitivity.py`, and the data-source field is in each file.

**S1. Mixing variance of M5.** The primary M5 uses one mixing variance, set by a rule before the grid ran. Here that variance is multiplied by 0.1, 1, 10 and 100, on the same simulated paths as the primary grid. The multiplier 1 row reproduces the primary M5 numbers exactly, which checks the script. No multiplier is proposed as a better default.

Share of runs that declared a winner, Scenario A (no effect):

| Mixing variance multiplier | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| 0.1 times | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| 1 (primary, pre-specified rule) | 0.0000 | 0.0000 | 0.0000 | 0.0010 | 0.0005 |
| 10 times | 0.0015 | 0.0050 | 0.0070 | 0.0135 | 0.0140 |
| 100 times | 0.0000 | 0.0020 | 0.0045 | 0.0115 | 0.0145 |

Share of runs that declared the correct winner, Scenario M(1.0) (`results/sensitivity_S1_M5_tau2.csv`):

| Mixing variance multiplier | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| 0.1 times | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| 1 (primary, pre-specified rule) | 0.0000 | 0.0015 | 0.0085 | 0.1110 | 0.4410 |
| 10 times | 0.0085 | 0.0370 | 0.1200 | 0.4165 | 0.8130 |
| 100 times | 0.0060 | 0.0300 | 0.0875 | 0.3660 | 0.7650 |

Mean total users at n = 50,000 in Scenario M(1.0) (undecided runs count as 2n): 90,650 at the primary variance, 62,354 at 10 times, and 62,056 at 100 times.

Reading S1: M5's low power in section 6.2 depends on the mixing variance. At 10 times the variance, its power at n = 50,000 is 0.8130 instead of 0.4410, and at n = 25,000 it is 0.4165 instead of 0.1110. Its false-positive rate in Scenario A stays at or below 0.0145 at every n and every multiplier tested. Power at 10 times the variance is still below M1's 0.9550 at n = 50,000, so the ranking of M5 against M1 on power does not change. The false-positive result (Q2) does not change.

**S2. Diagnostic for the R4 result.** At Scenario M(1.0) and Scenario A, n = 50,000, 500 repetitions, using the same random stream as R4 (`results/sensitivity_S2_R4_diagnostic_M1.0_n50000.json` and `results/sensitivity_S2_R4_diagnostic_A_n50000.json`). The results are described in section 6.7.

**S3. Feature-adjusted estimate on the whole held-out pool.** A regression of conversion on the treatment and the twelve standardized features, using all 11,183,674 rows of partition H, with no resampling. The treatment coefficient is 0.0924 points, against an unadjusted difference of 0.1153 points. The shift of -0.0229 points has the same direction as the shift in S2 (`results/sensitivity_S3_full_H_ols.json`). This is a check on the whole pool, not on the resampled tests. It is also in-sample for H, as every number is.

**S4. M6 with thresholds matched to a two-sided 0.05 per look.** M6 is rerun with thresholds 0.975 and 0.025 on the same cell paths as the primary grid, at the 500-user schedule and at 100 looks. Results (`results/sensitivity_S4_M6_matched_alpha.csv`). The 100-look and 500-user schedules coincide at n = 50,000.

Share of runs that declared a winner, Scenario A (no effect), with 95% Monte Carlo intervals:

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M6 as pre-specified (0.95 / 0.05) | 0.1380 | 0.2335 | 0.3465 | 0.4665 | 0.5140 |
| M6, matched (0.975 / 0.025), 500-user schedule | 0.0595 (0.0500 to 0.0707) | 0.1265 (0.1126 to 0.1418) | 0.1885 (0.1720 to 0.2062) | 0.2735 (0.2544 to 0.2935) | 0.3340 (0.3137 to 0.3550) |
| M6, matched, 100 looks | 0.0805 (0.0694 to 0.0932) | 0.1540 (0.1388 to 0.1705) | 0.2270 (0.2092 to 0.2459) | 0.2935 (0.2740 to 0.3138) | 0.3340 (0.3137 to 0.3550) |

Power, Scenario M(1.0), share of runs that declared the correct winner:

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M6 as pre-specified | 0.2295 | 0.4855 | 0.7020 | 0.9370 | 0.9945 |
| M6, matched, 500-user schedule | 0.1405 | 0.3245 | 0.5465 | 0.8720 | 0.9815 |
| M6, matched, 100 looks | 0.1795 | 0.3780 | 0.5840 | 0.8780 | 0.9815 |

Reading S4: matching the threshold to a two-sided 0.05 per look lowers M6's false-positive rate and its power at every n. At n = 50,000 the matched rate (0.334) is still far above 0.05, and it is close to M3 at 100 looks (0.3595). So the peeking problem is present at the matched threshold too. The difference between the primary M6 and M3 comes mostly from the doubled threshold.

**S5. Design inputs and descriptive numbers (arithmetic, no simulation).** `results/sensitivity_S5_design_inputs.json`.

- Closed-form sample size per arm, two-sided 0.05 and power 0.80: 29,624 at the observed unadjusted lift (59.5% relative), and 44,050 at the feature-adjusted effect of 0.0924 points (47.6% relative lift).
- Allocation: a 85:15 design needs 1.96 times the total users of a 1:1 design with the same variance.
- mSPRT threshold: with the variance set to the variance of the difference at the planned n, the rule needs |z| of about 3.66 at the planned n (the last look). A fixed two-sided test uses 1.96. Earlier looks have a larger variance, so they need a larger |z| still. The earlier-look thresholds are not computed in the results.
- Monte Carlo error at R = 2,000: 0.0049 at a rate of 0.05, 0.0107 at 0.36, and 0.0112 at 0.5. A difference between two independent rates at 0.05 is resolved only at about ±0.014, and at 0.5 only at about ±0.031 (95% level).
- Workload of the primary grid: 40,000 simulated paths, 240,000 rule evaluations, 4,416,000 look evaluations for M3, M5 and M6, 1.47 billion simulated users (2n per repetition, summed), and 73.6 million block-level count draws. The engine draws counts, not rows.

**S6. Alternative truth.** The true effect is set to the feature-adjusted estimate from S3 (0.0924 points). This is Scenario M(p) with p = 0.8012, which is the S3 estimate divided by the unadjusted difference. Every primary rule is run on new paths with this truth (`results/sensitivity_S6_alternative_truth.csv`).

Power (share of runs that declared the correct winner in the correct direction), with the true effect 0.0924 points:

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M1 fixed z | 0.0840 | 0.1565 | 0.2615 | 0.5635 | 0.8595 |
| M2 fixed Fisher | 0.0530 | 0.1090 | 0.2210 | 0.5205 | 0.8440 |
| M3 peeking z | 0.1370 | 0.2825 | 0.4375 | 0.7305 | 0.9105 |
| M4 group-seq OBF | 0.0820 | 0.1530 | 0.2530 | 0.5465 | 0.8495 |
| M5 mSPRT | 0.0000 | 0.0005 | 0.0030 | 0.0550 | 0.2170 |
| M6 Bayesian threshold | 0.1885 | 0.3770 | 0.5700 | 0.8175 | 0.9350 |

Mean total users (undecided runs count as 2n), and fraction undecided, with the same truth:

| Rule | n=2,000 | n=5,000 | n=10,000 | n=25,000 | n=50,000 |
|---|---|---|---|---|---|
| M1 fixed z | 4,000 (91% undecided) | 10,000 (84%) | 20,000 (74%) | 50,000 (44%) | 100,000 (14%) |
| M4 group-seq OBF | 3,967 (91%) | 9,800 (85%) | 19,218 (75%) | 44,955 (45%) | 79,260 (15%) |
| M6 Bayesian threshold | 3,703 (79%) | 7,913 (59%) | 12,943 (39%) | 20,183 (14%) | 25,122 (2%) |

Bias ratio and coverage at stop, with the same truth (n/e where fewer than 50 runs stopped): at n = 50,000, M1 has bias ratio 0.084 and coverage 0.9756; M4 has 0.182 and 0.9670; M6 has 0.865 and 0.9406. At n = 25,000, M1 has bias ratio 0.327 and coverage 0.9556. Bias ratios are larger than in section 6.4 at the same n, because the true effect is smaller, so the same absolute bias is a larger fraction of it. At n = 2,000 and 5,000 the bias ratios are large, as in section 6.4.

Reading S6: the power and time figures in section 6.2 and 6.3 depend on the truth. With the feature-adjusted truth, every rule needs more users for the same power. M1 reaches 0.86 power at n = 50,000, below the 0.955 of the unadjusted truth, and its closed-form n is about 44,050 per arm (S5). The ranking of rules is about the same. M6 still has the highest power at every n, partly because of its doubled error per look (S4), and M5 still has the lowest.

---

## 7. What failed, and what the review changed

These are failures and corrections during this run, and the corrections that followed an outside review on 2026-10-30. The full log is in `DESIGN.md` section 13 and section 13.5.

1. **Boundary check (V3) failed on the first run.** The first Python OBF spending formula used the wrong z value (the two-sided value where the one-sided form is needed), and the first bisection search went the wrong way. The check was then fixed and rerun. The gsDesign values were not changed. The second run passed with a largest difference of 0.00068. It was rerun on 2026-10-30 with the same result.
2. **Engine check at 500 repetitions looked off** (treated-arm variance about 2.4 Monte Carlo standard errors from direct row draws). At 6,000 repetitions the distributions agree (KS p-values 0.996 for control and 0.706 for treated). The first result was noise. The check covers one setting only (section 4.2).
3. **A stalled run.** The visit-outcome robustness run stalled for more than 15 minutes. The cause was the Beta-binomial tail call in scipy, which sums over the whole support for each element. That run was stopped and its output was not used. The call was replaced with an exact sum over the shorter tail, which agrees with scipy to about 2e-10 on valid inputs. The primary grid was rerun with the new code and reproduced every number exactly.
4. **Two unit-test inputs were invalid** (conversions larger than users). They were corrected. No rule output came from invalid inputs.
5. **R2 was not run**, because its design text cannot be applied as written (section 6.7).
6. **The design band is two-sided**, so conservative methods are classed as outside the band even though their error rate is below 0.05. M2 at n up to 10,000, and the Pocock variant at n = 2,000, are examples. The result is reported as measured.
7. **M5 has very low power at the chosen mixing variance.** It rarely stops before n = 25,000, even under the full observed effect. This is a null result for M5 under this mixing variance, and its cause is the threshold (section 4.3). The variance was fixed by a rule before the grid ran (`DESIGN.md` section 13.1), and it was not tuned to the results. A post hoc sensitivity analysis (S1) found that 10 times the variance raises M5's power at n = 50,000 from 0.441 to 0.813, while its Scenario A rate stays at or below 0.0145. The pre-specified result stays in the tables.
8. **Interval coverage at stop is naive for M3 to M6** because the Wald intervals are not adjusted for repeated looks. In Scenario A, coverage is 0 for M1 to M4 at every n. For M1, M3 and M4 this follows from the test itself (section 6.4). For M2 it is observed. Either way, coverage in Scenario A is uninformative.
9. **Provenance was added after the first run, and the first version was wrong.** The first `c9_provenance.py` gave the simulation fields (R, n grid, seed) to every file, including files that use no simulation. It also did not map the S3 file. The review found this. The script was rewritten. Files that use no simulation now say "not applicable". The script refuses to run if a file has no producer. No number changed.
10. **Console logs cited in the first version were not produced by any documented command.** The commands in section 3 now redirect output to the named log files.
11. **Post hoc analyses were added after the primary results were seen** (section 6.9). They are labelled as post hoc in every output file, and no pre-specified answer changed.
12. **M6 has a doubled error per look.** The review found that M6's thresholds (0.95 and 0.05) give a two-sided error of 0.10 per look, not 0.05. The first write-up compared it with M1 and M3 as if the error were the same. It is now stated in section 4.3 and in the table in section 6.1. The matched variant is S4. The claim that Bayesian peeking is worse than classical peeking was not supported after matching, and it was removed (section 6.6).
13. **The primary estimand has an unresolved choice.** The truth used for M(1.0) is the unadjusted difference, 0.1153 points. The feature-adjusted full-pool estimate is 0.0924 points (S3). The first write-up used only the unadjusted truth in its tables. S5 and S6 now show the effect of this choice. The unadjusted truth is kept as the primary truth, because it is the pre-specified one. Which truth is the "real" effect is not established.
14. **R4's "lower power" was scored against the wrong target.** The adjusted and unadjusted tests do not target the same quantity when effects differ across users (section 6.7). The power comparison in R4 is not like-for-like.
15. **Thin cells were reported as estimates.** M5 at n = 2,000, 5,000 and 10,000 had 0, 3 and 17 stopped runs in Scenario M(1.0). Their bias, coverage and sign agreement were shown as if they were estimates. They are now marked "n/e" (section 4.5), and the stop counts are in section 6.3.
16. **Monte Carlo error was understated.** The first write-up said "about 0.005 at each cell". The error is 0.011 near rates of 0.36 to 0.51. The resolution for a difference between two rates is about ±0.03 near 0.5. Section 6.1 and section 8 now say this.
17. **Q3 was overstated.** The first write-up said that "M4 has the shortest mean time at every n" and gave the answer as if all six rules were compared. Only two rules (or three from n = 25,000) are inside the band. The answer is now stated that way, with the percentage saving (section 6.6). The DESIGN section 13.3 wording was made consistent.
18. **The write-up said "real randomized data" without saying what the simulation uses.** The rules see only conversion counts drawn at two pooled real rates. Row order, features, time and test identity play no role. The first paragraph of this write-up now says so.
19. **DESIGN section 10 and the C4 workload claim overstated the work.** The engine draws counts, not rows, and the "1.5 billion row draws" figure is a count of simulated users. Both were corrected in DESIGN with dated notes, using the figures in S5.
20. **The DESIGN claim that the protocol was written before the results could not be verified.** Section 4 and section 13.1 of DESIGN.md are dated 2026-10-30, the day the grid ran. The protocol text is dated 2026-10-29. The status line of DESIGN.md said that no code had been run, which was false, and that was corrected.
21. **Pre-registration is not verifiable.** Before publication the project was not a git repository. The file times of DESIGN.md (01:58 on 2026-10-30) come after the primary grid (00:25). Git history starts at the publication commit on 2026-10-31, so the commit log cannot show that the protocol came before the results. The ordering is the author's statement only. This is a limitation (section 9).
22. **The gsDesign check printed its totals but did not assert them.** `src/c3_validate_R.R` now asserts that the null crossing totals equal the two-sided alpha to within 1e-6.
23. **Dependencies were unpinned.** `requirements.txt` now pins numpy 2.0.2, scipy 1.13.1 and pandas 2.3.3, and section 3 lists the R package versions.
24. **The 85:15 allocation was not listed as a limit.** It is now in section 6.3 and section 8, with the factor of 1.96.
25. **The design inputs came from counts that include H.** This is now stated in section 2. The closed-form sample size from H alone (29,624) and from the feature-adjusted effect (44,050) are both reported.
26. **Figure 1 had two colours that were hard to tell apart.** The palette was changed to Okabe-Ito with distinct shapes. Figures 3 and 4 leave out cells with fewer than 50 stops.
27. **The wording had figurative language.** "Budget" was replaced by "error allowance", and "urn" by "pool" in the engine docstring. No result changed.
28. **The engine check was described too broadly.** Section 4.2 now states the scope: one sample size, one p, final counts only, and the development partition D.

---

## 8. Limits

- **The data are not a startup's data.** Criteo is an advertising incrementality dataset. Its base rates (0.19% and 3.8%) and effect sizes are not typical of a startup product test. The results describe how the rules behave at these rates. They do not describe any company.
- **The rules see only counts, and users are assumed independent at a constant rate.** The simulation resamples real rows, but the rules use only the number of conversions per arm at each check. Row order, features, time and test identity play no role. There are no time trends, no novelty effects, and no within-test structure. A real test with any of these would behave differently.
- **Pooled tests.** The file pools several incrementality tests with no test ID. Randomization holds only inside each original test. The balance and sample ratio checks are the only protection, and they are limited. Every standardized difference is below 0.05, yet adding the features moves the full-pool estimate from 0.1153 to 0.0924 points (section 6.9, S3), so small feature differences matter for the estimate.
- **The truth is one of two estimates.** The primary truth is the unadjusted held-out difference (0.1153 points). The feature-adjusted estimate is 0.0924 points. Power, time, bias and coverage all depend on this choice. S5 and S6 give the second set of numbers. The true effect of the file is not established.
- **The file was subsampled by its source**, so the full-file ITT difference is the answer in this file, not necessarily the population answer.
- **The features are anonymized and projected.** Covariate adjustment (R4) is a sensitivity check only, and nothing here shows the features are pre-treatment.
- **One dataset, one effect size range.** The true effects in this study are 0, 0.25, 0.5 and 1.0 times the unadjusted held-out difference (plus the S6 truth). Other effect sizes and rates are not covered.
- **Allocation is 1:1 in the grid.** The source data were split 85:15. For the same variance, the 85:15 design needs about 1.96 times as many users in total (section 6.3).
- **Binary outcomes only.** Revenue and other continuous metrics are not covered.
- **Monte Carlo error.** With 2,000 repetitions, the standard error is 0.005 near a rate of 0.05 and 0.011 near 0.5. A difference between two independent rates is resolved only at about ±0.014 near 0.05, and about ±0.031 near 0.5 (95% level, S5). Smaller differences are not resolved. Wilson intervals for each cell are in `results/primary_grid.csv`.
- **Monte Carlo error is not the same as seed error.** A different seed would give different values inside the Monte Carlo intervals. The seeds are fixed by the protocol and were not changed after the review.
- **Normal approximations at low counts.** At n = 2,000 the control arm has about 4 conversions on average. The z-test and the Wald intervals are approximate in that regime. Fisher's test (M2) is the exact alternative and is conservative there.
- **Error levels differ between rules.** M6 has a two-sided error of 0.10 per look as pre-specified (section 4.3). M5 is approximate, because its variance is estimated at each look.
- **Mixing variance.** The M5 result depends on the mixing variance. The pre-specified choice is one of several reasonable ones, and section 6.9 (S1) shows how much the power changes across them.
- **Licence.** The dataset card on Hugging Face lists `cc-by-nc-sa-4.0`. No commercial use of this data, or of code adapted to it, is allowed (`DESIGN.md` section 2.3). The aggregate results and figures in `results/` and `figures/` are derived from the file and are shared under CC BY-NC-SA 4.0 with attribution to Diemert et al. (2018). The code has no licence file yet; the choice of code licence belongs to the author.

---

## 9. Limits and unresolved choices

Each item below is a limitation or a choice the write-up does not settle. None of them is fixed by a change to the numbers. Where the pre-set rules are not met, the result is reported as measured.

- **Pre-registration is not verified.** The protocol text in `DESIGN.md` is dated 2026-10-29, and the primary grid ran on 2026-10-30. The project was not a git repository before publication, so no record in the project shows the order. The ordering is the author's statement only. Git history starts at the publication commit on 2026-10-31 and does not reach back before it.
- **Q3 is not recalibrated to a common false-positive rate.** The time comparison is between rules at their own thresholds. A fair time comparison across rules would need each threshold tuned to the same false-positive rate. That would be a new analysis and is not in this write-up.
- **The truth for power and time is unresolved.** The primary truth is the unadjusted held-out difference (0.1153 points). The feature-adjusted full-pool estimate is 0.0924 points (S3). Power and time depend on which is used, and the write-up reports both (S5, S6). Which one is the real effect is not established.
- **R4's target is not established.** Whether the adjusted or the unadjusted estimate is the right target is not settled. The R4 power comparison should not be read as a finding about adjustment (section 6.7).
- **M3 at n = 2,000 depends on the seed.** Its Scenario A rate is 0.1070, with Monte Carlo interval 0.0942 to 0.1213. The rate is far above 0.05, so the conclusion does not depend on the seed. The exact value does, and the protocol seeds were not changed.
- **R2 is not run.** Its text in `DESIGN.md` cannot be applied as written, because drawing the treated arm from H-treated under Scenario A would create a real effect. The primary grid already uses equal arm sizes, so the 85:15 split does not enter any primary result (section 6.7).
