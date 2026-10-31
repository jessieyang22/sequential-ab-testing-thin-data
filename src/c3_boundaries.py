"""
C3 boundaries, computed independently in Python, then checked against gsDesign (check V3).

Method (Lan-DeMets alpha spending for K equally spaced looks, two-sided):
- The cumulative two-sided alpha to spend by look k is alpha(t_k), where t_k = k/K.
  OBF shape: alpha(t) = 4 - 4 * Phi(z / sqrt(t)), z = Phi^-1(1 - a/4).
  Pocock shape: alpha(t) = a * log(1 + (e - 1) * t).
- Under the null, the test statistics (Z_1..Z_K) have correlation
  corr(Z_i, Z_j) = sqrt(t_i / t_j) for i <= j.
- Look k's boundary c_k is chosen so that the probability of a first crossing
  at look k equals alpha(t_k) - alpha(t_{k-1}). The probability of "no crossing
  before k, and |Z_k| > c_k" is computed from orthant probabilities of a
  multivariate normal, using inclusion-exclusion over the 2^k corners of a box.

Output: results/python_boundaries.csv, and a comparison with gsDesign in
results/v3_boundary_check.json. The check passes if every boundary differs by
less than 0.001 on the z scale (DESIGN.md section 7).

Run from the repository root:  python3 src/c3_boundaries.py
"""

import itertools
import math
import os

import numpy as np
import pandas as pd
from scipy.stats import multivariate_normal, norm

from common import RESULTS, write_json

K = 5


def spend_cum(t, two_sided_alpha, shape):
    if shape == "OBF":
        # Two-sided total spend = 2 x one-sided spend. The one-sided spend uses
        # z = qnorm(1 - a1/2) with a1 = two_sided_alpha / 2, so z = qnorm(1 - a/4).
        # This matches gsDesign's sfLDOF with alpha = a/2 (checked in V3).
        z = norm.ppf(1 - two_sided_alpha / 4)
        return 4 - 4 * norm.cdf(z / math.sqrt(t))
    if shape == "Pocock":
        return two_sided_alpha * math.log(1 + (math.e - 1) * t)
    raise ValueError(shape)


def box_prob(bounds, cov):
    """P(|Z_j| < bounds_j for all j) for a centred multivariate normal with cov."""
    m = len(bounds)
    if m == 0:
        return 1.0
    total = 0.0
    for eps in itertools.product([0, 1], repeat=m):
        corner = np.array([-b if e else b for b, e in zip(bounds, eps)])
        sign = (-1) ** sum(eps)
        total += sign * multivariate_normal.cdf(corner, mean=np.zeros(m), cov=cov)
    return total


def solve_boundaries(two_sided_alpha, shape, K=K):
    t = np.arange(1, K + 1) / K
    cov_full = np.array([[math.sqrt(min(t[i], t[j]) / max(t[i], t[j])) for j in range(K)]
                         for i in range(K)])
    cum = [spend_cum(tk, two_sided_alpha, shape) for tk in t]
    inc = [cum[0]] + [cum[k] - cum[k - 1] for k in range(1, K)]
    bounds = []
    q_prev = 1.0                       # P(no crossing before look 1) = 1
    for k in range(K):
        target = q_prev - inc[k]       # P(no crossing up to and including look k) after spending
        lo, hi = 0.01, 10.0

        def q_of(c):
            b = bounds + [c]
            idx = list(range(k + 1))
            return box_prob(b, cov_full[np.ix_(idx, idx)])

        for _ in range(60):
            mid = 0.5 * (lo + hi)
            # q_of is increasing in c: a larger bound means more paths stay inside.
            if q_of(mid) > target:     # too many paths stay inside, so lower the bound
                hi = mid
            else:
                lo = mid
            if hi - lo < 1e-7:
                break
        c = 0.5 * (lo + hi)
        bounds.append(c)
        q_prev = target
    return bounds, cum


def main():
    rows = []
    for shape in ["OBF", "Pocock"]:
        for a in [0.05, 0.01]:
            b, cum = solve_boundaries(a, shape)
            for k in range(K):
                rows.append({"spending": shape, "two_sided_alpha": a, "look": k + 1,
                             "timing": (k + 1) / K, "upper_z_python": b[k],
                             "cum_alpha_target": cum[k]})
            print(shape, a, [round(x, 4) for x in b])
    py = pd.DataFrame(rows)
    py.to_csv(os.path.join(RESULTS, "python_boundaries.csv"), index=False)

    ref = pd.read_csv(os.path.join(RESULTS, "gsdesign_boundaries.csv"))
    merged = py.merge(ref, on=["spending", "two_sided_alpha", "look"], how="left")
    merged["abs_diff_z"] = (merged["upper_z_python"] - merged["upper_z"]).abs()
    worst = float(merged["abs_diff_z"].max())
    passed = bool(worst < 0.001)
    out = {"check": "V3", "tolerance_z": 0.001, "max_abs_diff_z": worst, "pass": passed,
           "rows_compared": int(len(merged)),
           "comparison": merged[["spending", "two_sided_alpha", "look", "upper_z_python",
                                 "upper_z", "abs_diff_z"]].to_dict(orient="records"),
           "script": "src/c3_boundaries.py", "reference": "results/gsdesign_boundaries.csv (gsDesign 3.11.0)"}
    write_json(os.path.join(RESULTS, "v3_boundary_check.json"), out)
    print("V3 max |diff| in z:", worst, "PASS" if passed else "FAIL")


if __name__ == "__main__":
    main()
