"""
Unit tests for the rules and the engine (DESIGN.md section 4, C3 unit tests).

Checks:
1. Beta-binomial identity for P(pC < pT) against Monte Carlo (10^6 draws).
2. Rules return "continue" when no data is given (all counts zero or empty look).
3. Smoke test: Scenario A false-positive rates at n = 2000 with R = 500, for every
   primary rule (reported only as a check that code runs; the grid is in c5).
4. The mSPRT log-likelihood ratio equals the closed form at d = 0 and is zero at V = 0.

Writes results/debug/unit_tests.txt. Exits nonzero on any failure.
Run from the repository root:  python3 src/c3_unit_tests.py
"""

import os
import sys

import numpy as np

from c3_rules import bayes_p_up, msprt_log_lambda, pooled_z
from common import RESULTS, load_pools, rates_from_pools

lines = []
failed = []


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    lines.append(f"[{tag}] {name} {detail}")
    if not ok:
        failed.append(name)


def main():
    rng = np.random.default_rng(1)
    # 1. Beta-binomial identity against Monte Carlo for a few parameter sets.
    cases = [(3, 1000, 7, 1500), (0, 2000, 4, 2000), (12, 5000, 20, 5000), (1, 200, 0, 300)]
    for xC, nC, xT, nT in cases:
        exact = float(bayes_p_up(np.array([xC]), np.array([nC]), np.array([xT]), np.array([nT]))[0])
        aC, bC = xC + 1, nC - xC + 1
        aT, bT = xT + 1, nT - xT + 1
        M = 1_000_000
        pC = rng.beta(aC, bC, M)
        pT = rng.beta(aT, bT, M)
        mc = float((pT > pC).mean())
        se = np.sqrt(mc * (1 - mc) / M)
        check(f"beta-binomial P(pT>pC) vs MC for counts {(xC, nC, xT, nT)}",
              abs(exact - mc) < 5 * se + 1e-4, f"exact={exact:.6f} mc={mc:.6f}")

    # 1b. Fast tail sum (used in the grid) against scipy's betabinom.sf, including visit-size counts.
    from c3_rules import betabinom_sf_ge
    from scipy.stats import betabinom as _bb
    worst = 0.0
    for n_test in [2000, 10000, 50000]:
        Lt = np.arange(500, n_test + 1, 500).astype(float)
        for rate in [0.0019, 0.0383, 0.0485]:
            nc = np.broadcast_to(Lt, (20, len(Lt))).copy()
            xc = np.minimum(rng.binomial(n_test, rate, nc.shape).astype(float), nc)   # conversions <= users
            xt = np.minimum(rng.binomial(n_test, rate, nc.shape).astype(float), nc)
            mine = bayes_p_up(xc, nc, xt, nc)
            ref = _bb.sf(xc, nc + 1, xt + 1, nc - xt + 1)     # P(BetaBinomial >= xC + 1)
            worst = max(worst, float(np.nanmax(np.abs(mine - ref))))
    check("fast beta-binomial tail sum matches scipy betabinom.sf (n up to 50,000)", worst < 1e-8,
          f"max abs diff={worst:.2e}")

    # 2. Continue with no data.
    z0 = pooled_z(np.array([0.0]), np.array([100.0]), np.array([0.0]), np.array([100.0]))
    check("pooled z with zero conversions returns 0 (no reject)", z0[0] == 0.0)
    l0 = msprt_log_lambda(np.array([0.0]), np.array([0.0]), 1e-6)
    check("mSPRT with zero variance returns log lambda 0 (continue)", l0[0] == 0.0)
    check("Bayesian rule with zero conversions gives P(up) finite", np.isfinite(
        bayes_p_up(np.array([0.0]), np.array([10.0]), np.array([0.0]), np.array([10.0]))[0]))

    # 3. mSPRT closed form at d = 0 should be 0.5 log(V/(V+tau2)).
    V, tau2 = 2e-4, 5e-5
    closed = 0.5 * np.log(V / (V + tau2))
    got = msprt_log_lambda(np.array([0.0]), np.array([V]), tau2)[0]
    check("mSPRT closed form at d = 0", abs(got - closed) < 1e-12, f"{got:.6f} vs {closed:.6f}")

    # 4. Smoke test of Scenario A false-positive rates at n = 2000, R = 500.
    from c5_score import PRIMARY_RULES, evaluate, rule_spec, summarise, true_effect
    from c4_engine import simulate_paths
    from common import read_json, load_pools as lp
    from c3_rules import msprt_tau2
    pools = lp()
    r0, _ = rates_from_pools(pools, "conversion")
    cumC, cumT = simulate_paths(np.random.default_rng(7), pools["conversion"], 0.0, 2000, 500)
    smoke = []
    for name in PRIMARY_RULES:
        spec = rule_spec(name, 2000)
        res = evaluate(spec, cumC, cumT, 2000, msprt_tau2(r0, 2000))
        smoke.append((name, float(res["fired"].mean())))
    lines.append("Smoke test, Scenario A, n = 2000, R = 500 (FPR by rule): " +
                 ", ".join(f"{a}={b:.3f}" for a, b in smoke))
    check("smoke test ran for all six rules", len(smoke) == 6)

    os.makedirs(os.path.join(RESULTS, "debug"), exist_ok=True)
    out = os.path.join(RESULTS, "debug", "unit_tests.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("Wrote", out)
    if failed:
        print("FAILED:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
