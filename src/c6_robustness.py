"""
C6: robustness checks (DESIGN.md section 4, C6). Each one is pre-specified.

R1 (visit outcome): the full primary grid with the visit outcome in place of conversion.
R2 (allocation): not run as a separate analysis. The design text for R2 draws the
   treated arm from H-treated under Scenario A, which would create a true effect and
   so conflicts with that scenario. The primary grid already uses equal arm sizes, so
   the 85/15 source split does not enter any primary result. Logged in DESIGN.md section 13.
R3 (schedule and alpha): (i) 100 looks at n/100 spacing for M3, M5, M6;
   (ii) alpha = 0.01 for M3, M4, M5, M6; plus the Pocock variant M4P. The R3 rules
   are evaluated on the same simulated paths as the primary grid (same seeds).
R4 (covariate adjustment, sensitivity only): regression adjustment on f0 to f11 with
   HC1 robust standard errors, compared with the unadjusted pooled z-test on the same
   real rows. Row-level draws are used here, because the features are needed.
   Labelled a sensitivity check. The features are anonymized and their timing relative
   to treatment is unknown.

Run from the repository root:  python3 src/c6_robustness.py [R1|R3|R4|all]
"""

import os
import sys
import time

import numpy as np
import pandas as pd

from c3_rules import pooled_z, z_crit
from c5_score import run_cell
from common import (CACHE, DATA_SOURCE, NS, R, RESULTS, SCENARIOS, SEED, cell_list, load_pools,
                    read_json)
from c5_score import PRIMARY_RULES

R3_RULES = ["M3_100", "M5_100", "M6_100", "M3_a01", "M4_a01", "M5_a01", "M6_a01", "M4P"]


def run_R1(pools, full_itt):
    rows = []
    for cell in [c for c in cell_list() if c["outcome"] == "visit"]:
        t = time.time()
        rows += run_cell(cell, pools, full_itt, PRIMARY_RULES)
        print("R1 cell", cell["scenario"], cell["n"], round(time.time() - t, 1), "s", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RESULTS, "robust_R1_visit_grid.csv"), index=False)
    print("R1 rows:", len(df))


def run_R3(pools, full_itt):
    rows = []
    for cell in [c for c in cell_list() if c["outcome"] == "conversion"]:
        rows += run_cell(cell, pools, full_itt, R3_RULES)
        print("R3 cell", cell["scenario"], cell["n"], flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RESULTS, "robust_R3_schedule_alpha.csv"), index=False)
    print("R3 rows:", len(df))


def sample_without_replacement(rng, pool, size):
    """Uniform sample of `size` distinct entries of `pool`.

    Draws with replacement and keeps the first `size` distinct values in order of
    first appearance. For i.i.d. draws, that order is a uniformly random order of
    the distinct values, so the result is a uniform sample without replacement.
    This avoids numpy's full permutation of a 1.7 million row pool at every repetition.
    """
    if size <= 0:
        return np.empty(0, dtype=np.int64)
    k = int(size * 1.2) + 50
    while True:
        draws = pool[rng.integers(0, len(pool), size=k)]
        _, first = np.unique(draws, return_index=True)
        if len(first) >= size:
            return draws[np.sort(first)[:size]]
        k *= 2


def run_R4():
    """CUPED-style regression adjustment on real rows, compared with the unadjusted test."""
    feats = np.load(os.path.join(CACHE, "features.npy"))
    treat = np.load(os.path.join(CACHE, "treatment.npy"))
    conv = np.load(os.path.join(CACHE, "conversion.npy"))
    H = np.load(os.path.join(CACHE, "H_mask.npy"))
    pools = load_pools()
    idx_c = np.flatnonzero(H & (treat == 0))
    idx_t = np.flatnonzero(H & (treat == 1))
    mu = feats[idx_c].mean(axis=0)
    sd = feats[idx_c].std(axis=0)
    rows = []
    for si, (scen, p) in enumerate(SCENARIOS):
        if scen == "M0.25":
            continue                    # R4 uses Scenarios A, M(0.5), M(1.0)
        for ni, n in enumerate(NS):
            print('R4 cell', scen, n, flush=True)
            seed = SEED + 100 + 10 * si + ni
            rng = np.random.default_rng(seed)
            zs_adj, zs_un = [], []
            for _ in range(R):
                nT1 = rng.binomial(n, p) if p > 0 else 0
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
                # Zero variance (no conversions in the sample) gives an undefined z. Count it as no reject.
                se_adj = np.sqrt(V[1, 1]) if V[1, 1] > 0 else np.nan
                z_adj = beta[1] / se_adj if np.isfinite(se_adj) else np.nan
                # Unadjusted: pooled z on the same rows.
                xC = y[:n].sum()
                xT = y[n:].sum()
                z_un = float(pooled_z(np.array([xC]), np.array([float(n)]), np.array([xT]), np.array([float(n)]))[0])
                zs_adj.append(z_adj)
                zs_un.append(z_un)
            zs_adj = np.array(zs_adj)
            zs_un = np.array(zs_un)
            crit = z_crit(0.05)
            for method, z in [("unadjusted pooled z", zs_un), ("regression adjusted (HC1)", zs_adj)]:
                z = np.asarray(z, dtype=float)
                rej = np.abs(z) > crit          # NaN compares as False, so an undefined z is no reject
                rows.append({"data_source": DATA_SOURCE, "scenario": scen, "p": p, "n_per_arm": n, "method": method,
                             "reject_rate": float(rej.mean()),
                             "positive_reject_rate": float((z > crit).mean()),
                             "undefined_z_count": int(np.isnan(z).sum()),
                             "reps": R, "seed": seed, "sensitivity_only": True})
        print("R4 done for", scen, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RESULTS, "robust_R4_cuped.csv"), index=False)
    print(df.to_string())


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.time()
    pools = load_pools()
    full_itt = read_json(os.path.join(RESULTS, "c1_pipeline.json"))["itt_full"]
    if which in ("R1", "all"):
        run_R1(pools, full_itt)
    if which in ("R3", "all"):
        run_R3(pools, full_itt)
    if which in ("R4", "all"):
        run_R4()
    print("done in", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
