"""
C5: run the simulation grid and score every rule against the known truth
(DESIGN.md sections 3.5, 4 C5, 5, 6 and 7).

Rules: M1 to M6 from DESIGN.md section 5. Their look schedules are:
- M1, M2: one look at n.
- M3, M5, M6: a look every 500 users per arm, up to n.
- M4: five equally spaced looks at n/5, 2n/5, ... n, with OBF boundaries from gsDesign.
- R3 variants live in c6_robustness.py and use the same simulated paths.

Metrics (per cell and rule): false-positive rate in Scenario A, power in the
correct direction in M(p), undecided fraction, time to decision, bias at stop,
interval coverage at stop, and agreement with the full-data ITT sign.

Checks written here:
- V2: M1 false-positive rate on Scenario A at n = 5000 is inside [0.035, 0.065].
  Also computes the exact false-positive rate for M1 and M2 at n = 2000 and 5000
  by summing over binomial probabilities, so the simulation can be compared with
  an exact value.
- V4: M5 false-positive rate on Scenario A is at most 0.065 at every n.

Run from the repository root:  python3 src/c5_score.py
"""

import json
import os
import time

import numpy as np
import pandas as pd
from scipy.stats import binom

from c3_rules import (bayes_p_up, first_stop, fisher_p, msprt_log_lambda, msprt_tau2,
                      pooled_z, wald, z_crit)
from c4_engine import cell_paths
from common import (BLOCK, DATA_SOURCE, NS, R, RESULTS, Z975, cell_list, load_pools,
                    rates_from_pools, read_json, wilson, write_json, git_note)

FPR_BAND = (0.035, 0.065)
GS_REF = os.path.join(RESULTS, "gsdesign_boundaries.csv")


def gs_bounds(spending, two_sided_alpha):
    ref = pd.read_csv(GS_REF)
    sub = ref[(ref["spending"] == spending) & (np.isclose(ref["two_sided_alpha"], two_sided_alpha))]
    sub = sub.sort_values("look")
    return sub["upper_z"].to_numpy()


def schedule(kind, n):
    if kind == "fixed":
        return np.array([n])
    if kind == "every500":
        return np.arange(500, n + 1, 500)
    if kind == "gs5":
        return np.array([n * k // 5 for k in range(1, 6)])
    if kind == "every_n_over_100":
        return np.array([n * k // 100 for k in range(1, 101)])
    raise ValueError(kind)


def rule_spec(name, n, alpha=0.05):
    """Specification of one rule (name, kind, look schedule, boundary, threshold)."""
    if name == "M1":
        return {"name": name, "kind": "z", "looks": schedule("fixed", n),
                "bounds": np.full(1, z_crit(alpha))}
    if name == "M2":
        return {"name": name, "kind": "fisher", "looks": schedule("fixed", n), "alpha": alpha}
    if name in ("M3", "M3_100", "M3_a01"):
        sched = "every_n_over_100" if name == "M3_100" else "every500"
        a = 0.01 if name == "M3_a01" else alpha
        L = schedule(sched, n)
        return {"name": name, "kind": "z", "looks": L, "bounds": np.full(len(L), z_crit(a))}
    if name in ("M4", "M4_a01", "M4P"):
        a = 0.01 if name == "M4_a01" else alpha
        spend = "Pocock" if name == "M4P" else "OBF"
        return {"name": name, "kind": "z", "looks": schedule("gs5", n),
                "bounds": gs_bounds(spend, a)}
    if name in ("M5", "M5_100", "M5_a01"):
        sched = "every_n_over_100" if name == "M5_100" else "every500"
        a = 0.01 if name == "M5_a01" else alpha
        return {"name": name, "kind": "msprt", "looks": schedule(sched, n), "alpha": a}
    if name in ("M6", "M6_100", "M6_a01", "M6_a025", "M6_100_a025"):
        # alpha is the per-look tail probability: stop if P(lift>0) > 1-alpha or < alpha.
        # M6 (0.95/0.05) is therefore 0.10 two-sided per look. M6_a025 (0.975/0.025) is the
        # post hoc variant matched to a two-sided 0.05 (added after the primary grid; S4).
        sched = "every_n_over_100" if name in ("M6_100", "M6_100_a025") else "every500"
        a = {"M6_a01": 0.01, "M6_a025": 0.025, "M6_100_a025": 0.025}.get(name, alpha)
        return {"name": name, "kind": "bayes", "looks": schedule(sched, n), "alpha": a}
    raise ValueError(name)


PRIMARY_RULES = ["M1", "M2", "M3", "M4", "M5", "M6"]


def evaluate(spec, cumC, cumT, n, tau2):
    """Run one rule on all R repetitions. Returns arrays of decisions and estimates."""
    L = spec["looks"]
    idx = L // BLOCK - 1
    K = len(L)
    xC = cumC[idx].T.astype(float)                 # shape (R, K)
    xT = cumT[idx].T.astype(float)
    nC = np.broadcast_to(L.astype(float), xC.shape)
    nT = nC
    Rn = xC.shape[0]
    rows = np.arange(Rn)
    d_all, se_all = wald(xC, nC, xT, nT)

    if spec["kind"] == "z":
        z = pooled_z(xC, nC, xT, nT)
        b = np.broadcast_to(spec["bounds"], z.shape)
        fire_pos = z > b
        fire_neg = z < -b
    elif spec["kind"] == "fisher":
        p = fisher_p(xC.ravel(), nC.ravel(), xT.ravel(), nT.ravel()).reshape(xC.shape)
        fire = p < spec["alpha"]
        fire_pos = fire & (d_all > 0)
        fire_neg = fire & (d_all < 0)
    elif spec["kind"] == "msprt":
        logL = msprt_log_lambda(d_all, se_all ** 2, tau2)
        thr = np.log(1.0 / spec["alpha"])
        fire_pos = (logL > thr) & (d_all > 0)
        fire_neg = (logL > thr) & (d_all < 0)
    elif spec["kind"] == "bayes":
        pu = bayes_p_up(xC, nC, xT, nT)
        fire_pos = pu > 1 - spec["alpha"]
        fire_neg = pu < spec["alpha"]
    else:
        raise ValueError(spec["kind"])

    fired, k, sign = first_stop(fire_pos, fire_neg)
    users = np.where(fired, 2 * L[k], 2 * n)
    d_stop = d_all[rows, k]
    se_stop = se_all[rows, k]
    return {"fired": fired, "k": k, "sign": sign, "users": users, "d_stop": d_stop,
            "lo": d_stop - Z975 * se_stop, "hi": d_stop + Z975 * se_stop, "looks_count": K}


def summarise(res, true_eff, full_itt_pp, n, reps):
    fired = res["fired"]
    nf = int(fired.sum())
    pos = int(((res["sign"] > 0) & fired).sum())
    neg = int(((res["sign"] < 0) & fired).sum())
    fr_lo, fr_hi = wilson(nf, reps)
    d = res["d_stop"][fired]
    out = {
        "reps": reps,
        "fired_rate": nf / reps, "fired_ci_lo": fr_lo, "fired_ci_hi": fr_hi,
        "positive_rate": pos / reps, "negative_rate": neg / reps,
        "undecided_rate": 1 - nf / reps,
        "mean_users_all_runs": float(res["users"].mean()),
        "median_users_stopped": float(np.median(res["users"][fired])) if nf > 0 else float("nan"),
        "n_stopped": nf,
        "mean_d_at_stop_pp": float(100 * d.mean()) if nf > 0 else float("nan"),
        "true_effect_pp": 100 * true_eff,
    }
    if nf > 0:
        out["bias_pp"] = out["mean_d_at_stop_pp"] - 100 * true_eff
        out["bias_ratio"] = (out["bias_pp"] / (100 * true_eff)) if true_eff != 0 else float("nan")
        cov = ((res["lo"][fired] <= true_eff) & (true_eff <= res["hi"][fired])).mean()
        out["coverage_at_stop"] = float(cov)
        out["sign_agree_full_itt"] = float((d > 0).mean())
        out["mean_abs_diff_full_itt_pp"] = float(np.abs(100 * d - full_itt_pp).mean())
    else:
        for key in ["bias_pp", "bias_ratio", "coverage_at_stop", "sign_agree_full_itt",
                    "mean_abs_diff_full_itt_pp"]:
            out[key] = float("nan")
    return out


def true_effect(pools, outcome, p):
    r0, r1 = rates_from_pools(pools, outcome)
    return p * (r1 - r0)


def run_cell(cell, pools, full_itt, rules, reps=R):
    """Simulate one cell once, then evaluate every rule on the same paths."""
    n, p, oc = cell["n"], cell["p"], cell["outcome"]
    cumC, cumT = cell_paths(pools, oc, p, n, cell["seed"], reps)
    r0, _ = rates_from_pools(pools, oc)
    tau2 = msprt_tau2(r0, n)
    tr = true_effect(pools, oc, p)
    rows = []
    for name in rules:
        spec = rule_spec(name, n)
        res = evaluate(spec, cumC, cumT, n, tau2)
        s = summarise(res, tr, full_itt[oc]["itt_diff_pp"], n, reps)
        s.update({"data_source": DATA_SOURCE, "outcome": oc, "scenario": cell["scenario"], "p": p, "n_per_arm": n,
                  "rule": name, "looks": len(spec["looks"]), "seed": cell["seed"],
                  "cell_index": cell["cell_index"], "msprt_tau2": tau2 if spec["kind"] == "msprt" else np.nan})
        rows.append(s)
    return rows


def exact_fpr(n, rate, alpha=0.05, M=80):
    """Exact false-positive rate of M1 and M2 when both arms have the same rate."""
    xs = np.arange(0, min(M, n) + 1)
    pm = binom.pmf(xs, n, rate)
    P = np.outer(pm, pm)
    XC, XT = np.meshgrid(xs, xs, indexing="ij")
    nC = np.full(XC.shape, float(n))
    z = pooled_z(XC.astype(float), nC, XT.astype(float), nC)
    m1 = float(P[np.abs(z) > z_crit(alpha)].sum())
    pf = fisher_p(XC.ravel().astype(float), nC.ravel(), XT.ravel().astype(float), nC.ravel()).reshape(XC.shape)
    m2 = float(P[pf < alpha].sum())
    return {"n_per_arm": n, "control_rate": rate, "exact_fpr_M1": m1, "exact_fpr_M2": m2,
            "mass_covered": float(P.sum())}


def main():
    t0 = time.time()
    pools = load_pools()
    c1 = read_json(os.path.join(RESULTS, "c1_pipeline.json"))
    full_itt = c1["itt_full"]
    os.makedirs(RESULTS, exist_ok=True)

    cells = [c for c in cell_list() if c["outcome"] == "conversion"]
    rows = []
    for cell in cells:
        rows += run_cell(cell, pools, full_itt, PRIMARY_RULES)
        print("done", cell["scenario"], cell["n"], round(time.time() - t0, 1), "s", flush=True)
    grid = pd.DataFrame(rows)

    # Band check per method in Scenario A (DESIGN.md section 7).
    A = grid["scenario"] == "A"
    grid["fpr_in_band_scenarioA"] = np.where(A, grid["fired_rate"].between(*FPR_BAND), np.nan)
    grid.to_csv(os.path.join(RESULTS, "primary_grid.csv"), index=False)

    # V2 and V4
    rA = grid[(grid["scenario"] == "A")]
    m1_5000 = float(rA[(rA["rule"] == "M1") & (rA["n_per_arm"] == 5000)]["fired_rate"].iloc[0])
    v2 = {"check": "V2", "value_M1_FPR_n5000": m1_5000, "band": FPR_BAND,
          "pass": bool(FPR_BAND[0] <= m1_5000 <= FPR_BAND[1])}
    m5 = rA[rA["rule"] == "M5"].sort_values("n_per_arm")
    v4 = {"check": "V4", "value_M5_FPR_by_n": dict(zip(m5["n_per_arm"].astype(int), m5["fired_rate"])),
          "band_max": 0.065, "pass": bool((m5["fired_rate"] <= 0.065).all())}
    r0, _ = rates_from_pools(pools, "conversion")
    exact = [exact_fpr(n, r0) for n in [2000, 5000]]
    v2["exact_check"] = exact
    v2["exact_M1_within_band"] = bool(FPR_BAND[0] <= exact[1]["exact_fpr_M1"] <= FPR_BAND[1])

    write_json(os.path.join(RESULTS, "checks_V2_V4.json"), {"V2": v2, "V4": v4,
               "script": "src/c5_score.py", "seed_note": "seed = SEED + cell_index",
               "git_commit": git_note()})
    print("V2:", json.dumps(v2, indent=1, default=float))
    print("V4:", json.dumps(v4, indent=1, default=float))
    print("Wrote", os.path.join(RESULTS, "primary_grid.csv"), "in", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
