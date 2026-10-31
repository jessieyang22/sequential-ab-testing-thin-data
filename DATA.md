# Data: what was downloaded and what the file contains

This file records what was observed in the raw data. Every number below comes from `results/data_profile.json`, which was written by `src/data_profile.py`. The protocol is in `DESIGN.md`. This file does not compare treatment and control for any result. The comparisons come later.

Last profile run: 2026-10-30 03:22 UTC (the `run_utc` field in `results/data_profile.json`).

---

## 1. Source

| Item | Value |
|---|---|
| Dataset | Criteo Uplift Modeling Dataset, version 2.1 (research uplift v2.1) |
| Citation | Diemert, E., Betlei, A., Renaudin, C., and Amini, M.-R. (2018). *A Large Scale Benchmark for Uplift Modeling.* AdKDD and TargetAd Workshop, KDD 2018. |
| Dataset page | https://huggingface.co/datasets/criteo/criteo-uplift |
| Direct file URL | https://huggingface.co/datasets/criteo/criteo-uplift/resolve/main/criteo-research-uplift-v2.1.csv.gz |
| License | CC BY-NC-SA 4.0 (non-commercial, share-alike, attribution required). See `DESIGN.md` section 2.3. |
| Local copy | `data/raw/criteo-research-uplift-v2.1.csv.gz` (git-ignored, not committed) |
| Compressed size | 311,422,618 bytes |
| Uncompressed size | 3,248,115,221 bytes (measured 2026-10-29 with `gzip -dc`) |
| SHA-256 | `2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc` |

### How to get the data

From the repository root:

```
pip install -r requirements.txt
./data/download.sh
python3 src/data_profile.py
```

Versions used: Python 3.9.6 (the macOS system Python), pandas 2.3.3. `requirements.txt` asks for pandas 2.0 or later.

`download.sh` fetches the file into `data/raw/`. It checks the byte count, the SHA-256, and gzip integrity. If a valid copy is already present, it does nothing. A mismatch deletes the download and stops with an error.

Test on 2026-10-29: the script was run once with the raw folder empty. The download took about 1 minute 42 seconds. It printed `Verified (size, SHA-256, gzip integrity)`. The profile script was then run on the same file and matched every count in `DESIGN.md` section 2.4.

---

## 2. Data dictionary

Each row is one user in one randomized test. There is no user ID, no test ID, and no timestamp.

| Column | Type | Meaning in this file | Observed values |
|---|---|---|---|
| `f0` to `f11` | float (continuous) | Twelve anonymized features. The dataset card says they are randomly projected, so the original meanings and units are not available. They are not known to be measured before treatment. | Continuous. Ranges in section 4. |
| `treatment` | 0 or 1 | 1 = the user was assigned to receive ads. 0 = the user was held out (no ads). This is the assignment, so it is the basis of the intention-to-treat (ITT) comparison. | 0, 1 |
| `conversion` | 0 or 1 | 1 = the user converted (purchase or other target action) in the test window. The test window length is not stated in the file. | 0, 1 |
| `visit` | 0 or 1 | 1 = the user visited the advertiser's site in the test window. | 0, 1 |
| `exposure` | 0 or 1 | 1 = the user was actually shown an ad. This is only defined in the treated arm. | 0, 1 |

Plain-English note on `exposure`: a user can be assigned to ads and still not be shown one, for example because the ad system did not win an auction for that user. The `exposure` column is 0 for every control user, so it cannot be used to compare shown and not-shown users within the control arm. `DESIGN.md` section 3.4 explains why the study uses ITT and not an exposure-based estimate.

---

## 3. Row counts, date range, and missingness (as observed)

### 3.1 Row counts

| Item | Value | Check |
|---|---|---|
| Total rows (users) | 13,979,592 | Matches the dataset card and `DESIGN.md` |
| Treated users (`treatment` = 1) | 11,882,655 | |
| Control users (`treatment` = 0) | 2,096,937 | |
| Treated share | 85.00% | `DESIGN.md` assumed 0.85. Observed 0.8500001. |
| Treated conversions | 36,711 | |
| Control conversions | 4,063 | |
| Treated visits | 576,824 | |
| Control visits | 80,105 | |
| Treated users with `exposure` = 1 | 428,212 (3.60%) | |
| Control users with `exposure` = 1 | 0 | Confirms the note in section 2 |

### 3.2 Base rates observed

| Outcome | Control rate | Treated rate |
|---|---|---|
| Conversion | 0.1938% (4,063 of 2,096,937) | 0.3089% (36,711 of 11,882,655) |
| Visit | 3.82% | 4.85% |
| Exposure | 0 (by definition) | 3.60% |

These match the counts in `DESIGN.md` section 2.4. Conversion rates are shown here as observed. No test of the difference is reported in this file.

### 3.3 Date range

**None.** The file has no timestamp, date, or week column. The earliest and latest dates of the test cannot be determined from the file. Any statement about time (for example, "this test ran in 2017") would be an assumption, not a fact from this data. The write-up must say so.

### 3.4 Missingness

| Column group | Missing values | Share missing |
|---|---|---|
| `f0` to `f11` (12 columns) | 0 each | 0% |
| `treatment`, `conversion`, `visit`, `exposure` | 0 each | 0% |

No cell in the file is empty or non-numeric. The profile script reads every value as a float, so a text value would have stopped the run.

### 3.5 Other structural checks observed

| Check | Result |
|---|---|
| `conversion` = 1 but `visit` = 0 | 0 rows |
| `exposure` ≠ 0 in a control row | 0 rows |
| Values of `treatment`, `conversion`, `visit`, `exposure` | Only 0 and 1 |
| Header matches the column list | Yes |
| Rows match the dataset card | Yes (13,979,592) |

---

## 4. Feature ranges (observed, full file)

Values are the minimum and maximum seen in all 13,979,592 rows. Missing values: none.

| Feature | Min | Max |
|---|---|---|
| f0 | 12.6164 | 26.7453 |
| f1 | 10.0597 | 16.3442 |
| f2 | 8.2144 | 9.0520 |
| f3 | -8.3984 | 4.6799 |
| f4 | 10.2805 | 21.1235 |
| f5 | -9.0119 | 4.1155 |
| f6 | -31.4298 | 0.2944 |
| f7 | 4.8338 | 11.9984 |
| f8 | 3.6351 | 3.9719 |
| f9 | 13.1901 | 75.2950 |
| f10 | 5.3004 | 6.4739 |
| f11 | -1.3839 | -0.1687 |

Several features have a narrow range (for example f8 and f10), and f9 has a long upper tail. The file does not say what the features measure. Any covariate adjustment (robustness check R4 in `DESIGN.md`) is a sensitivity check only.

---

## 5. Partitions (sizes only)

The split is defined in `DESIGN.md` section 3.1. Seed 20261029, random permutation, first 20% = development partition D, remaining 80% = held-out partition H. Only the sizes are recorded here. No row-level index file is written, because a row-level file derived from the data would fall under the share-alike term of the license.

| Partition | Rows | Use |
|---|---|---|
| D (development) | 2,795,918 | Writing and debugging code only. No reported number. |
| H (held-out) | 11,183,674 | All reported numbers. |

The partition is created in the component C1 script, not in this profile step. Balance and sample-ratio checks (C1) have not been run yet.

---

## 6. Limits of this description

- The treated share is almost exactly 0.85. Expected treated users at exactly 0.85 would be 11,882,653.2. Observed is 11,882,655, which is about 2 users more. This suggests the source set the ratio when it sub-sampled the file. If so, the sample-ratio check in C1 will pass, and it cannot show whether pooling the tests broke randomization.
- The file contains no dates, so the study cannot say when the tests ran.
- The file pools several incrementality tests with no test ID. Randomization is only guaranteed inside each original test. Section 2.4 of `DESIGN.md` explains this, and the balance and SRM checks in C1 are the only check on whether pooling broke randomization.
- The features are anonymized and projected. Their meaning, units, and timing relative to treatment are unknown.
- The dataset is advertising incrementality data. Its base rates and effect sizes are not those of a typical startup product test.
- License: non-commercial only. See `DESIGN.md` section 2.3.
