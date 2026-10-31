"""
Answers to the pre-specified questions Q1 to Q4 (DESIGN.md section 6).
Every value is read from a results file. Nothing is typed by hand.

Writes results/answers.json.
Run from the repository root after c5_score.py, c6_robustness.py, c10_sensitivity.py and c2_power.py:
    python3 src/c8_answers.py
"""

import os

import pandas as pd

from common import RESULTS, NS, read_json, wilson, write_json

FPR_BAND = (0.035, 0.065)


def main():
    grid = pd.read_csv(os.path.join(RESULTS, "primary_grid.csv"))
    r3 = pd.read_csv(os.path.join(RESULTS, "robust_R3_schedule_alpha.csv"))
    c2 = read_json(os.path.join(RESULTS, "c2_power_check.json"))
    v = read_json(os.path.join(RESULTS, "checks_V2_V4.json"))
    out = {"script": "src/c8_answers.py"}

    # Q1: is the FPR of M3 (peeking) inflated above 0.05 at the 100-look schedule?
    # Supported if FPR >= 0.10 and the 95% Monte Carlo interval lies entirely above 0.07.
    q1 = []
    for n in NS:
        row = r3[(r3.scenario == "A") & (r3.rule == "M3_100") & (r3.n_per_arm == n)].iloc[0]
        lo, hi = wilson(round(row.fired_rate * row.reps), row.reps)
        q1.append({"n_per_arm": n, "fpr": float(row.fired_rate), "ci": [lo, hi],
                   "supported": bool(row.fired_rate >= 0.10 and lo > 0.07)})
    out["Q1_M3_100_look_FPR_by_n"] = q1
    out["Q1_headline_n"] = 50000
    out["Q1_supported_at_headline_n"] = next(x["supported"] for x in q1 if x["n_per_arm"] == 50000)

    # Q2: does M5 or M6 keep the FPR at or below 0.05 under peeking?
    q2 = []
    for rule in ["M5", "M6"]:
        for n in NS:
            row = grid[(grid.scenario == "A") & (grid.rule == rule) & (grid.n_per_arm == n)].iloc[0]
            q2.append({"rule": rule, "n_per_arm": n, "fpr_primary_schedule": float(row.fired_rate),
                       "looks": int(row.looks)})
        for n in NS:
            row = r3[(r3.scenario == "A") & (r3.rule == f"{rule}_100") & (r3.n_per_arm == n)].iloc[0]
            q2.append({"rule": f"{rule} (100 looks)", "n_per_arm": n,
                       "fpr_primary_schedule": float(row.fired_rate), "looks": int(row.looks)})
    out["Q2_FPR"] = q2
    # Post hoc S4: M6 with thresholds matched to a two-sided 0.05 per look (0.975 / 0.025).
    s4 = pd.read_csv(os.path.join(RESULTS, "sensitivity_S4_M6_matched_alpha.csv"))
    out["Q2_post_hoc_S4_M6_matched"] = [
        {"rule": r.rule, "scenario": r.scenario, "n_per_arm": int(r.n_per_arm),
         "fired_rate": float(r.fired_rate), "fired_ci": [float(r.fired_ci_lo), float(r.fired_ci_hi)],
         "positive_rate": float(r.positive_rate), "mean_users_all_runs": float(r.mean_users_all_runs)}
        for r in s4.itertuples()]

    # Q3: shortest time to decision at the same FPR (methods inside the FPR band only).
    # Scenario M(1.0), conversion. Metric: mean total users over all runs (undecided at 2n).
    q3 = []
    for n in NS:
        sub = grid[(grid.scenario == "M1.0") & (grid.n_per_arm == n)].copy()
        fpr = grid[(grid.scenario == "A") & (grid.n_per_arm == n)][["rule", "fired_rate"]]
        sub = sub.merge(fpr.rename(columns={"fired_rate": "fpr_A"}), on="rule")
        inband = sub[sub.fpr_A.between(*FPR_BAND)]
        best = inband.sort_values("mean_users_all_runs").iloc[0] if len(inband) else None
        m1 = sub[sub.rule == "M1"].iloc[0]
        m4 = sub[sub.rule == "M4"].iloc[0]
        q3.append({"n_per_arm": n,
                   "in_band_rules": inband.rule.tolist(),
                   "M4_vs_M1_mean_users_saving_pct": float(100 * (1 - m4.mean_users_all_runs / m1.mean_users_all_runs)),
                   "M4_mean_users_all_runs": float(m4.mean_users_all_runs),
                   "M4_undecided_rate": float(m4.undecided_rate),
                   "M1_undecided_rate": float(m1.undecided_rate),
                   "fastest_in_band": None if best is None else best.rule,
                   "fastest_mean_users_all_runs": None if best is None else float(best.mean_users_all_runs),
                   "M1_mean_users_all_runs": float(m1.mean_users_all_runs),
                   "M1_positive_rate": float(m1.positive_rate),
                   "undecided_by_rule": {r: float(x) for r, x in zip(sub.rule, sub.undecided_rate)}})
    out["Q3_time_to_decision"] = q3

    # Q4: does M1's power at the calculated n match the simulation?
    out["Q4_C2_check"] = {"pass": c2["pass"], "simulated_power": c2["simulated_power_M1"],
                          "band_3se": c2["band_3se"], "n_per_arm": c2["n_per_arm_simulated"]}

    # Post hoc S6: all primary rules with the alternative truth (S3 feature-adjusted estimate).
    s6 = pd.read_csv(os.path.join(RESULTS, "sensitivity_S6_alternative_truth.csv"))
    out["S6_alternative_truth"] = [
        {"rule": r.rule, "n_per_arm": int(r.n_per_arm), "true_effect_pp": float(r.true_effect_pp),
         "positive_rate": float(r.positive_rate), "n_stopped": int(r.n_stopped),
         "mean_users_all_runs": float(r.mean_users_all_runs),
         "bias_ratio": None if pd.isna(r.bias_ratio) else float(r.bias_ratio),
         "coverage_at_stop": None if pd.isna(r.coverage_at_stop) else float(r.coverage_at_stop)}
        for r in s6.itertuples()]
    out["S5_design_inputs"] = read_json(os.path.join(RESULTS, "sensitivity_S5_design_inputs.json"))

    out["V2"] = v["V2"]
    out["V4"] = v["V4"]
    write_json(os.path.join(RESULTS, "answers.json"), out)
    print("Q1 at n=50000 supported:", out["Q1_supported_at_headline_n"])
    print("Q4 pass:", c2["pass"])
    print("Wrote", os.path.join(RESULTS, "answers.json"))


if __name__ == "__main__":
    main()
