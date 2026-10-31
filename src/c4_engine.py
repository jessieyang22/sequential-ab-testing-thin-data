"""
C4: resampling engine over the real held-out rows (DESIGN.md section 4, C4).

What the engine does, in plain terms:
- A simulated experiment draws real users from the held-out partition H,
  without replacement inside one repetition. Each user's conversion (or visit)
  flag is a real value from the file.
- The stopping rules only use the number of conversions per arm at each look.
  The row features are never used by these rules. So the engine draws, for each
  block of users, how many converters the draw contains. Given the pool sizes
  and the pool conversion counts, that count follows a hypergeometric
  distribution. This is the exact distribution of the count under sampling
  without replacement from the real rows, so the method is a computational
  shortcut and not synthetic data. Check C4-debug (below) compares it with
  drawing real row numbers directly.
- Arms and pools: control users come from H-control. Treated users are drawn
  one at a time: with probability p the user comes from H-treated, otherwise
  from H-control. Scenario A has p = 0 (no effect). Scenario M(p) has true
  effect p * (rate_treated - rate_control) in H.
- Within a repetition, all draws share one pool per source group, so no user is drawn
  twice in one run. Both arms advance together in blocks of BLOCK users.

Output of simulate_paths: cumulative conversion counts for each arm after every
block of BLOCK users per arm. Every rule reads its counts from these arrays.
Because all rules read the same arrays, they share draws (common random numbers).

Run as a script to run the debug check on the development partition D
(writes results/debug/engine_check_D.json; not used for any reported number):
    python3 src/c4_engine.py
"""

import json
import os

import numpy as np

from common import BLOCK, CACHE, RESULTS, load_pools, write_json


def simulate_paths(rng, pool, p, n, R, block=BLOCK):
    """Simulate R repetitions of a two-arm experiment with n users per arm.

    pool: dict with N0, K0 (H-control size and conversions) and N1, K1 (H-treated).
    p: probability that a treated-arm user comes from H-treated.
    Returns cumC, cumT: arrays of shape (n // block, R) with cumulative conversions
    for control and treated after each block.
    """
    nb = n // block
    N0 = np.full(R, pool["N0"], dtype=np.int64)
    K0 = np.full(R, pool["K0"], dtype=np.int64)
    N1 = np.full(R, pool["N1"], dtype=np.int64)
    K1 = np.full(R, pool["K1"], dtype=np.int64)
    cumC = np.zeros((nb, R), dtype=np.int32)
    cumT = np.zeros((nb, R), dtype=np.int32)
    cC = np.zeros(R, dtype=np.int64)
    cT = np.zeros(R, dtype=np.int64)
    for b in range(nb):
        # Control arm: `block` users from H-control.
        sC = rng.hypergeometric(K0, N0 - K0, block)
        N0 = N0 - block
        K0 = K0 - sC
        # Treated arm: each user goes to H-treated with probability p.
        if p > 0:
            nT1 = rng.binomial(block, p, size=R)
        else:
            nT1 = np.zeros(R, dtype=np.int64)
        s1 = rng.hypergeometric(K1, N1 - K1, nT1)
        N1 = N1 - nT1
        K1 = K1 - s1
        nT0 = block - nT1
        s0 = rng.hypergeometric(K0, N0 - K0, nT0)
        N0 = N0 - nT0
        K0 = K0 - s0
        cC = cC + sC
        cT = cT + s1 + s0
        cumC[b] = cC
        cumT[b] = cT
    return cumC, cumT


def cell_paths(pools, outcome, p, n, seed, R_reps):
    """Paths for one cell. The same seed always gives the same paths."""
    rng = np.random.default_rng(seed)
    return simulate_paths(rng, pools[outcome], p, n, R_reps)


def debug_check_row_vs_engine(pools_D_path, n=2000, R_reps=500, seed=999, p=0.5):
    """Compare final conversion counts from the engine with drawing real D rows.

    This uses the development partition only (debugging). Row-level draws use the
    cached conversion column and the cached treatment column, selecting rows of D.
    Writes a summary to results/debug/engine_check_D.json.
    """
    from scipy.stats import ks_2samp

    pools_D = json.load(open(pools_D_path))
    treat = np.load(os.path.join(CACHE, "treatment.npy"), mmap_mode="r")
    conv = np.load(os.path.join(CACHE, "conversion.npy"), mmap_mode="r")
    mask_H = np.load(os.path.join(CACHE, "H_mask.npy"), mmap_mode="r")
    dev = ~np.asarray(mask_H)
    t = np.asarray(treat)
    c = np.asarray(conv)
    idx_c0 = np.flatnonzero(dev & (t == 0))
    idx_t1 = np.flatnonzero(dev & (t == 1))
    rng_row = np.random.default_rng(seed)
    final_row_C = np.empty(R_reps, dtype=np.int64)
    final_row_T = np.empty(R_reps, dtype=np.int64)
    for r in range(R_reps):
        nT1 = rng_row.binomial(n, p)
        # Control-pool users: all n control-arm users plus the (n - nT1) treated-arm users
        # that come from H-control. Drawn without replacement, then split.
        ctrl_pool_draw = rng_row.choice(idx_c0, size=2 * n - nT1, replace=False)
        trt_pool_draw = rng_row.choice(idx_t1, size=nT1, replace=False)
        ctrl_arm = ctrl_pool_draw[:n]
        trt_arm = np.concatenate([trt_pool_draw, ctrl_pool_draw[n:]])
        final_row_C[r] = c[ctrl_arm].sum()
        final_row_T[r] = c[trt_arm].sum()

    cumC, cumT = simulate_paths(np.random.default_rng(seed + 1), pools_D["conversion"], p, n, R_reps)
    eng_C = cumC[-1].astype(float)
    eng_T = cumT[-1].astype(float)
    res = {
        "partition": "D (development, debugging only; not a reported result)",
        "n_per_arm": n, "p": p, "reps": R_reps,
        "row_draw_mean_control": float(final_row_C.mean()),
        "engine_mean_control": float(eng_C.mean()),
        "row_draw_mean_treated": float(final_row_T.mean()),
        "engine_mean_treated": float(eng_T.mean()),
        "row_draw_var_treated": float(final_row_T.var(ddof=1)),
        "engine_var_treated": float(eng_T.var(ddof=1)),
        "ks_stat_control": float(ks_2samp(final_row_C, eng_C).statistic),
        "ks_p_control": float(ks_2samp(final_row_C, eng_C).pvalue),
        "ks_stat_treated": float(ks_2samp(final_row_T, eng_T).statistic),
        "ks_p_treated": float(ks_2samp(final_row_T, eng_T).pvalue),
    }
    return res


if __name__ == "__main__":
    dbg_dir = os.path.join(RESULTS, "debug")
    out = debug_check_row_vs_engine(os.path.join(CACHE, "pools_D_debug_only.json"), R_reps=6000)
    write_json(os.path.join(dbg_dir, "engine_check_D.json"), out)
    print(json.dumps(out, indent=2))
