"""
C10: sensitivity analyses added after the primary grid was run (DESIGN.md section 13.4).

Both analyses are post hoc. They were not in the protocol and were decided after the
primary results were seen. Their outputs are labelled as such in every file.

S1 (mSPRT mixing variance). The primary M5 uses tau2 = 2 r_C (1 - r_C) / n (fixed rule).
   This script multiplies that tau2 by 0.1, 1, 10 and 100, on the same simulated paths
   as the primary grid (same cell seeds, conversion outcome, Scenarios A and M(1.0),
   every n, 500-user look schedule). The multiplier 1 row must reproduce the primary
   M5 numbers exactly. This is a check of the script, not a new result.
   No multiplier is chosen as a better default, and no Q1 to Q4 answer changes.

S2 (regression adjustment diagnostic, R4). At Scenario M(1.0) and n = 50,000, the
   R4 adjusted estimate is compared with the unadjusted difference over repeated draws.
   Logged quantities: the spread (SD over repetitions) of each estimate, the mean
   standard error each one reports, and the ratio of the adjusted to unadjusted values.
   This tests whether the lower adjusted power comes from extra variance in the
   estimate or from an inflated standard error.

S3 (full-pool check). Feature-adjusted OLS on all rows of H, no resampling.

S4 (M6 matched alpha). The primary M6 stops when P(lift > 0) > 0.95 or < 0.05, which is a
   two-sided 0.10 per look. S4 reruns M6 with thresholds 0.975 and 0.025 (two-sided 0.05
   per look) on the same cell paths as the primary grid, at every look schedule and n.

S5 (design inputs and descriptive numbers). Closed-form sample size at the S3 effect, the
   1:1 versus 85:15 allocation factor, the |z| that the mSPRT rule needs at its planned n,
   the Monte Carlo resolution at R = 2,000, and the simulation workload. These are
   arithmetic on fixed inputs, not new simulations.

S6 (alternative truth). Scenario M(p) with p chosen so that the true effect equals the
   S3 feature-adjusted estimate (about 0.0924 points) instead of the unadjusted 0.1153.
   Every primary rule is run on new paths with that truth, so power, time, bias and
   coverage can be read against it.

Run from the repository root:  python3 src/c10_sensitivity.py [S1|S2|S3|S4|S5|S6|all]
"""

import os
import sys
import time

import numpy as np
import pandas as pd

import math

from scipy.optimize import brentq

from c3_rules import pooled_z, z_crit
from c4_engine import cell_paths
from c5_score import PRIMARY_RULES, evaluate, rule_spec, run_cell, summarise
from c6_robustness import sample_without_replacement
from common import (ALLOCATION_TREATED_SHARE, ALPHA, BLOCK, CACHE, NS, R, RESULTS, SEED, cell_list,
                    load_pools, rates_from_pools, read_json, wilson, write_json, git_note)
from c3_rules import msprt_tau2

MULTIPLIERS = [0.1, 1.0, 10.0, 100.0]
S1_SCENARIOS = ["A", "M1.0"]
S2_REPS = 500
LABEL = "POST HOC SENSITIVITY (added after the primary grid; not in the protocol)"
from common import DATA_SOURCE


def run_S1():
    pools = load_pools()
    rows = []
    for cell in [c for c in cell_list() if c["outcome"] == "conversion" and c["scenario"] in S1_SCENARIOS]:
        n, p = cell["n"], cell["p"]
        cumC, cumT = cell_paths(pools, "conversion", p, n, cell["seed"], R)
        r0, _ = rates_from_pools(pools, "conversion")
        base_tau2 = msprt_tau2(r0, n)
        for mult in MULTIPLIERS:
            spec = rule_spec("M5", n)
            res = evaluate(spec, cumC, cumT, n, base_tau2 * mult)
            fired = res["fired"]
            pos = int(((res["sign"] > 0) & fired).sum())
            rows.append({
                "analysis": "S1 post hoc", "data_source": DATA_SOURCE, "scenario": cell["scenario"], "p": p,
                "n_per_arm": n, "rule": "M5", "tau2_multiplier": mult,
                "tau2": base_tau2 * mult, "reps": R, "seed": cell["seed"],
                "fired_rate": float(fired.mean()),
                "positive_rate": pos / R,
                "undecided_rate": float(1 - fired.mean()),
                "mean_users_all_runs": float(res["users"].mean()),
            })
            print("S1", cell["scenario"], n, mult, rows[-1]["fired_rate"], rows[-1]["positive_rate"], flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RESULTS, "sensitivity_S1_M5_tau2.csv"), index=False)
    return df


def run_S2(p=1.0, si=3, scen="M1.0"):
    feats = np.load(os.path.join(CACHE, "features.npy"))
    treat = np.load(os.path.join(CACHE, "treatment.npy"))
    conv = np.load(os.path.join(CACHE, "conversion.npy"))
    H = np.load(os.path.join(CACHE, "H_mask.npy"))
    pools = load_pools()
    idx_c = np.flatnonzero(H & (treat == 0))
    idx_t = np.flatnonzero(H & (treat == 1))
    mu = feats[idx_c].mean(axis=0)
    sd = feats[idx_c].std(axis=0)
    n = 50000
    seed = SEED + 100 + 10 * si + NS.index(n)     # same stream as R4 for this scenario and n
    rng = np.random.default_rng(seed)
    beta_adj, se_adj_list, diff_un, se_un_list, z_adj, z_un = [], [], [], [], [], []
    for _ in range(S2_REPS):
        nT1 = rng.binomial(n, p)
        ctrl_pool = sample_without_replacement(rng, idx_c, 2 * n - nT1)
        trt_pool = sample_without_replacement(rng, idx_t, nT1)
        ctrl_arm = ctrl_pool[:n]
        trt_arm = np.concatenate([trt_pool, ctrl_pool[n:]])
        rows_idx = np.concatenate([ctrl_arm, trt_arm])
        y = conv[rows_idx].astype(float)
        tr = np.concatenate([np.zeros(n), np.ones(n)])
        X = np.column_stack([np.ones(2 * n), tr, (feats[rows_idx] - mu) / sd])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        e = y - X @ beta
        XtX_inv = np.linalg.inv(X.T @ X)
        meat = (X * e[:, None] ** 2).T @ X
        V = XtX_inv @ meat @ XtX_inv * (2 * n) / (2 * n - X.shape[1])
        s_a = np.sqrt(V[1, 1]) if V[1, 1] > 0 else np.nan
        beta_adj.append(beta[1])
        se_adj_list.append(s_a)
        z_adj.append(beta[1] / s_a if np.isfinite(s_a) else np.nan)
        yC, yT = y[:n], y[n:]
        d = yT.mean() - yC.mean()
        s_u = np.sqrt(yT.var(ddof=1) / n + yC.var(ddof=1) / n)
        diff_un.append(d)
        se_un_list.append(s_u)
        z_un.append(d / s_u if s_u > 0 else np.nan)
    beta_adj = np.array(beta_adj)
    diff_un = np.array(diff_un)
    se_adj_list = np.array(se_adj_list, dtype=float)
    se_un_list = np.array(se_un_list, dtype=float)
    z_adj = np.array(z_adj, dtype=float)
    z_un = np.array(z_un, dtype=float)
    crit = z_crit(0.05)
    out = {
        "analysis": "S2 post hoc diagnostic", "label": LABEL, "data_source": DATA_SOURCE,
        "scenario": scen, "p": p, "n_per_arm": n, "reps": S2_REPS, "seed": seed,
        "true_effect": float(p * (rates_from_pools(pools, "conversion")[1] - rates_from_pools(pools, "conversion")[0])),
        "mean_adjusted_coefficient": float(np.mean(beta_adj)),
        "mean_unadjusted_difference": float(np.mean(diff_un)),
        "sd_adjusted_coefficient": float(np.std(beta_adj, ddof=1)),
        "sd_unadjusted_difference": float(np.std(diff_un, ddof=1)),
        "sd_ratio_adjusted_over_unadjusted": float(np.std(beta_adj, ddof=1) / np.std(diff_un, ddof=1)),
        "mean_se_adjusted_HC1": float(np.nanmean(se_adj_list)),
        "mean_se_unadjusted": float(np.mean(se_un_list)),
        "se_ratio_adjusted_over_unadjusted": float(np.nanmean(se_adj_list) / np.mean(se_un_list)),
        "reject_rate_unadjusted_two_sided": float((np.abs(z_un) > crit).mean()),
        "reject_rate_adjusted_two_sided": float((np.abs(z_adj) > crit).mean()),
        "undefined_z_adjusted": int(np.isnan(z_adj).sum()),
        "undefined_z_unadjusted": int(np.isnan(z_un).sum()),
        "script": "src/c10_sensitivity.py",
        "git": git_note(),
    }
    print(out, flush=True)
    write_json(os.path.join(RESULTS, f"sensitivity_S2_R4_diagnostic_{scen}_n50000.json"), out)
    return out


def run_S3():
    """Full-H feature-adjusted OLS: does adjustment move the estimate on the whole held-out pool?"""
    feats = np.load(os.path.join(CACHE, "features.npy"), mmap_mode="r")
    treat = np.load(os.path.join(CACHE, "treatment.npy"), mmap_mode="r")
    conv = np.load(os.path.join(CACHE, "conversion.npy"), mmap_mode="r")
    H = np.load(os.path.join(CACHE, "H_mask.npy"), mmap_mode="r")
    Hidx = np.flatnonzero(np.asarray(H))
    ctrl = Hidx[np.asarray(treat[Hidx]) == 0]
    mu = np.asarray(feats[ctrl], dtype=float).mean(axis=0)
    sd = np.asarray(feats[ctrl], dtype=float).std(axis=0)
    k = 14
    XtX = np.zeros((k, k))
    Xty = np.zeros(k)
    sum_c = [0.0, 0.0]; cnt_c = [0, 0]; sum_t = [0.0, 0.0]; cnt_t = [0, 0]
    chunk = 1_000_000
    for i in range(0, len(Hidx), chunk):
        ix = Hidx[i:i + chunk]
        tr = np.asarray(treat[ix], dtype=float)
        y = np.asarray(conv[ix], dtype=float)
        Z = (np.asarray(feats[ix], dtype=float) - mu) / sd
        X = np.column_stack([np.ones(len(ix)), tr, Z])
        XtX += X.T @ X
        Xty += X.T @ y
        cnt_t[0] += tr.sum(); sum_t[0] += (y * tr).sum()
        cnt_c[0] += (1 - tr).sum(); sum_c[0] += (y * (1 - tr)).sum()
    beta = np.linalg.solve(XtX, Xty)
    unadj = sum_t[0] / cnt_t[0] - sum_c[0] / cnt_c[0]
    out = {"analysis": "S3 post hoc check (full held-out pool, no resampling)", "label": LABEL,
           "data_source": "all rows of partition H (real data, not resampled, not synthetic)",
           "n_rows": int(len(Hidx)), "unadjusted_itt_pp": float(100 * unadj),
           "feature_adjusted_treatment_coef_pp": float(100 * beta[1]),
           "shift_pp": float(100 * (beta[1] - unadj)),
           "script": "src/c10_sensitivity.py", "git": git_note()}
    print(out, flush=True)
    write_json(os.path.join(RESULTS, "sensitivity_S3_full_H_ols.json"), out)
    return out


def run_S4(pools, full_itt):
    """M6 at two-sided 0.05 per look (0.975 / 0.025), next to the primary M6 (0.95 / 0.05)."""
    rules = ["M6", "M6_a025", "M6_100_a025"]
    rows = []
    for cell in [c for c in cell_list() if c["outcome"] == "conversion" and c["scenario"] in ("A", "M1.0")]:
        for r in run_cell(cell, pools, full_itt, rules):
            r["analysis"] = "S4 post hoc (M6 threshold matched to two-sided 0.05 per look)"
            r["label"] = LABEL
            rows.append(r)
        print("S4", cell["scenario"], cell["n"], flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RESULTS, "sensitivity_S4_M6_matched_alpha.csv"), index=False)
    return df


def alt_truth_p(pools):
    """Scenario p whose true effect equals the S3 feature-adjusted estimate (exact value)."""
    s3 = read_json(os.path.join(RESULTS, "sensitivity_S3_full_H_ols.json"))
    eff = s3["feature_adjusted_treatment_coef_pp"] / 100.0
    r0, r1 = rates_from_pools(pools, "conversion")
    return eff / (r1 - r0), eff


def run_S6(pools, full_itt):
    """All primary rules on new paths whose true effect is the S3 estimate."""
    p_alt, eff = alt_truth_p(pools)
    rows = []
    for ni, n in enumerate(NS):
        cell = {"outcome": "conversion", "scenario": "M_alt (S3 truth)", "p": p_alt, "n": n,
                "seed": SEED + 500 + ni, "cell_index": f"S6-{ni}"}
        for r in run_cell(cell, pools, full_itt, PRIMARY_RULES):
            r["analysis"] = "S6 post hoc (true effect = S3 feature-adjusted estimate)"
            r["label"] = LABEL
            rows.append(r)
        print("S6", n, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RESULTS, "sensitivity_S6_alternative_truth.csv"), index=False)
    return df


def run_S5(pools):
    """Design inputs and descriptive numbers. Arithmetic on fixed inputs; no simulation."""
    from scipy.stats import norm
    r0, r1 = rates_from_pools(pools, "conversion")
    alpha, power = ALPHA, 0.80
    za, zb = norm.ppf(1 - alpha / 2), norm.ppf(power)

    def closed_form_n(a, b):
        return (za + zb) ** 2 * (a * (1 - a) + b * (1 - b)) / (a - b) ** 2

    _, eff = alt_truth_p(pools)
    # mSPRT: the rule fires when log(LR) > log(1/alpha). With tau2 equal to the variance V of
    # the difference at the planned n, log(LR) = -0.5 log 2 + z^2 / 4, where z = d / sqrt(V).
    thr = math.log(1 / ALPHA)
    z_msprt = brentq(lambda z: -0.5 * math.log(2) + z * z / 4 - thr, 0.1, 10)
    # Monte Carlo resolution at R repetitions.
    def mc_se(p):
        return math.sqrt(p * (1 - p) / R)
    out = {
        "analysis": "S5 post hoc design inputs and descriptive numbers (no simulation)",
        "label": LABEL, "data_source": "closed-form arithmetic on fixed inputs from partition H counts",
        "control_rate_H": r0, "treated_rate_H": r1,
        "closed_form_n_per_arm_observed_H_lift": closed_form_n(r0, r1),
        "closed_form_n_per_arm_S3_effect": closed_form_n(r0, r0 + eff),
        "S3_effect_pp": 100 * eff,
        "S3_relative_lift": eff / r0,
        "allocation_factor_85_15_vs_1to1_same_variance": (1 / ALLOCATION_TREATED_SHARE + 1 / (1 - ALLOCATION_TREATED_SHARE)) / 4,
        "msprt_implied_abs_z_threshold_at_planned_n": z_msprt,
        "msprt_note": "tau2 = V at the planned n; the threshold is the same at every n for that matching",
        "monte_carlo_se_at_p_0.05": mc_se(0.05),
        "monte_carlo_se_at_p_0.36": mc_se(0.36),
        "monte_carlo_se_at_p_0.5": mc_se(0.5),
        "resolution_two_rates_p_0.05_95pct": 1.96 * math.sqrt(2) * mc_se(0.05),
        "resolution_two_rates_p_0.5_95pct": 1.96 * math.sqrt(2) * mc_se(0.5),
        "primary_grid_paths": 4 * len(NS) * R,
        "primary_grid_rule_evaluations": 4 * len(NS) * R * len(PRIMARY_RULES),
        "look_evaluations_per_path_M3_M5_M6": sum(n // 500 for n in NS),
        "look_evaluations_total_M3_M5_M6": 3 * R * 4 * sum(n // 500 for n in NS),
        "simulated_users_total_conversion_grid": 4 * R * sum(2 * n for n in NS),
        "block_steps_total_conversion_grid": 4 * R * sum(n // BLOCK for n in NS),
        "script": "src/c10_sensitivity.py",
    }
    print(out, flush=True)
    write_json(os.path.join(RESULTS, "sensitivity_S5_design_inputs.json"), out)
    return out


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.time()
    if which in ("S1", "all"):
        run_S1()
    if which in ("S2", "all"):
        run_S2(1.0, 3, "M1.0")
        run_S2(0.0, 0, "A")
    if which in ("S3", "all"):
        run_S3()
    if which in ("S4", "all"):
        run_S4(load_pools(), read_json(os.path.join(RESULTS, "c1_pipeline.json"))["itt_full"])
    if which in ("S5", "all"):
        run_S5(load_pools())
    if which in ("S6", "all"):
        run_S6(load_pools(), read_json(os.path.join(RESULTS, "c1_pipeline.json"))["itt_full"])
    print("done in", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
