"""
C2: power and sample-size calculator (DESIGN.md section 4, C2).

Step 1 (closed form): per-arm sample size for a two-proportion test, two-sided alpha 0.05,
power 0.80, at the real control rate from H, for relative lifts 15%, 30%, and the lift
observed in H. Computed for conversion (primary) and visit (secondary).

Step 2 (check): simulate the fixed-horizon z-test (M1) in Scenario M(1.0) at the
calculated n for the observed conversion lift. The calculator passes if the simulated
power is within 3 Monte Carlo SEs of 0.80 (DESIGN.md section 7).

Run from the repository root:  python3 src/c2_power.py
"""

import math
import os

import numpy as np
import pandas as pd
from scipy.stats import norm

from c3_rules import pooled_z, z_crit
from c4_engine import simulate_paths
from common import BLOCK, R, RESULTS, SEED, load_pools, rates_from_pools, write_json


def closed_form_n(p1, p2, alpha=0.05, power=0.80):
    za = norm.ppf(1 - alpha / 2)
    zb = norm.ppf(power)
    return (za + zb) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2)) / (p1 - p2) ** 2


def main():
    pools = load_pools()
    rows = []
    for outcome in ["conversion", "visit"]:
        r0, r1 = rates_from_pools(pools, outcome)
        observed_lift = r1 / r0 - 1
        for label, lift in [("15%", 0.15), ("30%", 0.30), ("observed in H", observed_lift)]:
            p2 = r0 * (1 + lift)
            n = closed_form_n(r0, p2)
            rows.append({"outcome": outcome, "lift_label": label, "relative_lift": lift,
                         "control_rate": r0, "treated_rate": p2, "n_per_arm_closed_form": n,
                         "n_per_arm_rounded_up": int(math.ceil(n))})
    tbl = pd.DataFrame(rows)
    tbl.to_csv(os.path.join(RESULTS, "c2_sample_size.csv"), index=False)
    print(tbl.to_string())

    # Step 2: simulated power of M1 at the calculated n for the observed conversion lift.
    obs = tbl[(tbl.outcome == "conversion") & (tbl.lift_label == "observed in H")].iloc[0]
    n_calc = int(math.ceil(obs["n_per_arm_closed_form"] / BLOCK) * BLOCK)
    seed = SEED + 60                      # reserved cell index 60 (DESIGN.md 3.5 convention)
    rng = np.random.default_rng(seed)
    cumC, cumT = simulate_paths(rng, pools["conversion"], 1.0, n_calc, R)
    xC = cumC[-1].astype(float)
    xT = cumT[-1].astype(float)
    nn = np.full(R, float(n_calc))
    z = pooled_z(xC, nn, xT, nn)
    power_sim = float((z > z_crit(0.05)).mean())
    se = math.sqrt(0.8 * 0.2 / R)
    passed = bool(abs(power_sim - 0.80) <= 3 * se)
    out = {"check": "C2", "scenario": "M1.0 (resampled real rows)", "outcome": "conversion",
           "n_per_arm_calculated": float(obs["n_per_arm_closed_form"]),
           "n_per_arm_simulated": n_calc, "reps": R, "seed": seed,
           "simulated_power_M1": power_sim, "target_power": 0.80,
           "monte_carlo_se_at_0.80": se, "band_3se": [0.80 - 3 * se, 0.80 + 3 * se],
           "pass": passed, "script": "src/c2_power.py"}
    write_json(os.path.join(RESULTS, "c2_power_check.json"), out)
    print("C2 check:", out["simulated_power_M1"], "band", out["band_3se"], "PASS" if passed else "FAIL")


if __name__ == "__main__":
    main()
