"""
C1: data pipeline and randomization checks (DESIGN.md section 4, C1).

Steps, in plain terms:
1. Read the raw Criteo file once and save each column as a compact binary
   array in data/raw/cache/ (git-ignored). The raw file is never copied anywhere else.
2. Shuffle all row numbers with the fixed seed. The first 20% become the
   development partition D (debugging only). The rest is the held-out
   partition H (every reported number).
3. Balance check on H: standardized mean difference (SMD) of each feature
   between treated and control.
4. Sample ratio mismatch (SRM) check: is the treated share 0.85?
5. V1 check: is the held-out ITT difference inside the full-data 95% interval?
6. Save aggregate counts ("pools") for H, which the simulation engine uses.
   Only counts are saved in results/. Row-level arrays stay in data/raw/cache/.

Run from the repository root:  python3 src/c1_pipeline.py
"""

import math
import os
import time

import numpy as np
import pandas as pd
from scipy.stats import chi2

from common import (ALLOCATION_TREATED_SHARE, CACHE, DEV_FRAC, FEATURES, N_ROWS,
                    RAW, RESULTS, SEED, Z975, git_note, write_json)

CACHE_NAMES = ["features", "treatment", "conversion", "visit", "exposure"]
OUTCOME_COLS = ["conversion", "visit"]


def cache_paths():
    return {k: os.path.join(CACHE, k + ".npy") for k in CACHE_NAMES}


def build_cache():
    """One pass over the raw CSV. Writes int8 columns and float32 features."""
    paths = cache_paths()
    if all(os.path.exists(p) for p in paths.values()):
        print("Cache already present; reusing it.")
        return paths
    os.makedirs(CACHE, exist_ok=True)
    feats = np.empty((N_ROWS, len(FEATURES)), dtype=np.float32)
    ints = {c: np.empty(N_ROWS, dtype=np.int8) for c in ["treatment", "conversion", "visit", "exposure"]}
    pos = 0
    for chunk in pd.read_csv(RAW, compression="gzip", chunksize=1_000_000, dtype=float):
        m = len(chunk)
        end = pos + m
        feats[pos:end] = chunk[FEATURES].to_numpy(dtype=np.float32)
        for c in ints:
            ints[c][pos:end] = chunk[c].to_numpy().astype(np.int8)
        pos = end
    if pos != N_ROWS:
        raise SystemExit(f"Row count {pos} does not match {N_ROWS}")
    np.save(paths["features"], feats)
    for c in ints:
        np.save(paths[c], ints[c])
    print("Cache written to", CACHE)
    return paths


def pool_counts(mask, treat, outcome_arr):
    """Counts for one outcome inside a boolean mask of rows."""
    ctrl = mask & (treat == 0)
    trt = mask & (treat == 1)
    return {
        "N0": int(np.count_nonzero(ctrl)),
        "K0": int(np.count_nonzero(ctrl & (outcome_arr == 1))),
        "N1": int(np.count_nonzero(trt)),
        "K1": int(np.count_nonzero(trt & (outcome_arr == 1))),
    }


def itt_summary(pc):
    """ITT difference in rates (treated minus control) with a normal 95% CI."""
    r0 = pc["K0"] / pc["N0"]
    r1 = pc["K1"] / pc["N1"]
    diff = r1 - r0
    se = math.sqrt(r1 * (1 - r1) / pc["N1"] + r0 * (1 - r0) / pc["N0"])
    return {"control_rate": r0, "treated_rate": r1, "itt_diff": diff,
            "itt_diff_pp": 100 * diff, "se_pp": 100 * se,
            "ci_lo_pp": 100 * (diff - Z975 * se), "ci_hi_pp": 100 * (diff + Z975 * se),
            "relative_lift": diff / r0}


def srm_test(n_treated, n_total):
    """Chi-square goodness-of-fit of the treated share against 0.85 (DESIGN.md C1)."""
    e1 = ALLOCATION_TREATED_SHARE * n_total
    e0 = (1 - ALLOCATION_TREATED_SHARE) * n_total
    n0 = n_total - n_treated
    stat = (n_treated - e1) ** 2 / e1 + (n0 - e0) ** 2 / e0
    return {"treated_share": n_treated / n_total, "chi2": float(stat),
            "p_value": float(chi2.sf(stat, 1))}


def main():
    t0 = time.time()
    paths = build_cache()
    treat = np.load(paths["treatment"])
    arrs = {c: np.load(paths[c]) for c in ["conversion", "visit", "exposure"]}
    feats = np.load(paths["features"])

    # Random split (DESIGN.md 3.1). Permutation of all row numbers with fixed seed.
    rng = np.random.default_rng(SEED)
    perm = rng.permutation(N_ROWS)
    n_dev = int(math.floor(DEV_FRAC * N_ROWS))
    held = np.zeros(N_ROWS, dtype=bool)
    held[perm[n_dev:]] = True
    dev = ~held
    del perm
    np.save(os.path.join(CACHE, "H_mask.npy"), held)
    print(f"Split: D = {int(dev.sum()):,} rows, H = {int(held.sum()):,} rows")

    full_mask = np.ones(N_ROWS, dtype=bool)
    out = {
        "script": "src/c1_pipeline.py",
        "seed": SEED,
        "git_commit": git_note(),
        "partition_sizes": {"D": int(dev.sum()), "H": int(held.sum())},
    }

    # Balance on H (SMD per feature). Pre-set rule: |SMD| > 0.1 is flagged.
    tr_h = held & (treat == 1)
    co_h = held & (treat == 0)
    rows = []
    for j, name in enumerate(FEATURES):
        x = feats[:, j].astype(np.float64)
        mt, vt = x[tr_h].mean(), x[tr_h].var(ddof=1)
        mc, vc = x[co_h].mean(), x[co_h].var(ddof=1)
        smd = (mt - mc) / math.sqrt((vt + vc) / 2)
        rows.append({"feature": name, "mean_treated_H": mt, "mean_control_H": mc, "smd_H": smd,
                     "flagged": bool(abs(smd) > 0.1)})
    bal = pd.DataFrame(rows)
    os.makedirs(RESULTS, exist_ok=True)
    bal.to_csv(os.path.join(RESULTS, "c1_balance.csv"), index=False)
    n_flag = int(bal["flagged"].sum())
    out["balance_H"] = {"features_flagged": n_flag,
                        "max_abs_smd": float(bal["smd_H"].abs().max()),
                        "flagged_features": bal.loc[bal["flagged"], "feature"].tolist(),
                        "label": ("the full-data answer in this file, not a causal effect"
                                  if n_flag > 2 else "no label needed (2 or fewer features flagged)")}

    # SRM on the full file and on H.
    out["srm_full"] = srm_test(int(np.count_nonzero(treat == 1)), N_ROWS)
    out["srm_H"] = srm_test(int(np.count_nonzero(tr_h)), int(held.sum()))

    # Pools and ITT for each outcome (full file, H, and D for debugging only).
    pools_H, pools_full, pools_D = {}, {}, {}
    for oc in OUTCOME_COLS:
        pools_full[oc] = pool_counts(full_mask, treat, arrs[oc])
        pools_H[oc] = pool_counts(held, treat, arrs[oc])
        pools_D[oc] = pool_counts(dev, treat, arrs[oc])
    out["pools_full"] = pools_full
    out["pools_H"] = pools_H
    out["itt_full"] = {oc: itt_summary(pools_full[oc]) for oc in OUTCOME_COLS}
    out["itt_H"] = {oc: itt_summary(pools_H[oc]) for oc in OUTCOME_COLS}

    # V1 (DESIGN.md 3.3 and 7): H-only ITT must lie inside the full-data 95% CI.
    f = out["itt_full"]["conversion"]
    h = out["itt_H"]["conversion"]
    v1_pass = f["ci_lo_pp"] <= h["itt_diff_pp"] <= f["ci_hi_pp"]
    out["V1"] = {"full_ci_pp": [f["ci_lo_pp"], f["ci_hi_pp"]], "H_itt_pp": h["itt_diff_pp"],
                 "pass": bool(v1_pass)}

    # Debug-only pools for D, kept in the cache folder and not used in any result.
    write_json(os.path.join(CACHE, "pools_D_debug_only.json"), pools_D)

    out["run_seconds"] = round(time.time() - t0, 1)
    write_json(os.path.join(RESULTS, "c1_pipeline.json"), out)

    print("Full-data ITT (conversion, pp):", round(f["itt_diff_pp"], 4),
          "CI", [round(f["ci_lo_pp"], 4), round(f["ci_hi_pp"], 4)])
    print("H-only ITT (conversion, pp):", round(h["itt_diff_pp"], 4), "V1 pass:", v1_pass)
    print("Balance flagged on H:", n_flag, "max |SMD|:", round(out["balance_H"]["max_abs_smd"], 4))
    print("SRM full p:", out["srm_full"]["p_value"], " SRM H p:", out["srm_H"]["p_value"])
    print("Wrote", os.path.join(RESULTS, "c1_pipeline.json"))


if __name__ == "__main__":
    main()
