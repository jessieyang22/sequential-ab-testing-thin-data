"""
C3: stopping rules (DESIGN.md section 4, C3, and section 5 table).

Every rule takes cumulative counts at a set of looks and returns, for each
simulated run and each look, whether it would stop in the positive direction
and whether it would stop in the negative direction.

Notation: xC, nC = control conversions and users so far; xT, nT = treated.
d = pT - pC is the estimated lift.

Plain-English summary of each rule:
- pooled_z: two-proportion z-test with a pooled variance under no effect.
  A zero denominator (no conversions at all, or every user converted) gives z = 0,
  which means "do not stop". This is stated in the write-up.
- wald: the usual unpooled standard error for d, used for the 95% interval at stop.
- msprt_log_lambda: log of the mixture likelihood ratio. The mixing variance tau2
  is fixed per cell (see msprt_tau2). Stop when the ratio is above 1/alpha.
  With a plug-in variance V = 0 the rule "continues" (ratio = 1).
- bayes_p_up: posterior probability that pT > pC, with independent Beta(1,1)
  priors. Computed exactly, not by simulation, using the identity
  P(pC < pT) = P(BetaBinomial(nC + 1, aT, bT) >= aC), with aC = xC + 1,
  bC = nC - xC + 1 (and the same for T). This identity holds for Beta
  distributions with positive integer parameters, and it is checked against
  Monte Carlo in c3_unit_tests.py.
"""

import math

import numpy as np
from scipy.stats import betabinom, fisher_exact, norm


def pooled_z(xC, nC, xT, nT):
    xC, nC, xT, nT = (np.asarray(a, dtype=float) for a in (xC, nC, xT, nT))
    pC = xC / nC
    pT = xT / nT
    p = (xC + xT) / (nC + nT)
    se = np.sqrt(p * (1 - p) * (1 / nC + 1 / nT))
    ok = se > 0
    return np.where(ok, (pT - pC) / np.where(ok, se, 1.0), 0.0)


def wald(xC, nC, xT, nT):
    xC, nC, xT, nT = (np.asarray(a, dtype=float) for a in (xC, nC, xT, nT))
    pC = xC / nC
    pT = xT / nT
    d = pT - pC
    se = np.sqrt(pT * (1 - pT) / nT + pC * (1 - pC) / nC)
    return d, se


def msprt_tau2(rate_control, n_planned):
    """Mixing variance for the difference in proportions (fixed per cell).

    Rule: tau2 = variance of the difference at the planned per-arm size n, under
    the control rate. Chosen before the grid was run (logged in DESIGN.md section 13).
    """
    return 2.0 * rate_control * (1 - rate_control) / n_planned


def msprt_log_lambda(d, V, tau2):
    """log of the normal-mixture likelihood ratio for a difference d with variance V."""
    d = np.asarray(d, dtype=float)
    V = np.asarray(V, dtype=float)
    Vs = np.where(V > 0, V, 1.0)
    logL = 0.5 * np.log(Vs / (Vs + tau2)) + tau2 * d * d / (2 * Vs * (Vs + tau2))
    return np.where(V > 0, logL, 0.0)


def betabinom_sf_ge(a, m, al, be, chunk=2000):
    """P(BetaBinomial(m, al, be) >= a), summing only over the shorter tail.

    scipy's betabinom.sf sums over the whole support for each element, which is
    too slow at visit-size counts (up to 50,001 trials). This version starts from
    the log of the first pmf term and adds log ratios with a cumulative sum:
        pmf(j+1) / pmf(j) = (m - j) (j + al) / ((j + 1) (m - j + be - 1)).
    It sums the lower tail (j < a) or the upper tail (j >= a), whichever has fewer
    terms. Checked against betabinom.sf in c3_unit_tests.py.
    """
    from scipy.special import betaln, gammaln
    a = np.asarray(a, dtype=float).ravel()
    m = np.asarray(m, dtype=float).ravel()
    al = np.asarray(al, dtype=float).ravel()
    be = np.asarray(be, dtype=float).ravel()
    out = np.empty(a.shape[0])
    for start in range(0, a.shape[0], chunk):
        sl = slice(start, min(start + chunk, a.shape[0]))
        aa, mm, aal, bbe = a[sl], m[sl], al[sl], be[sl]
        use_lower = aa <= (mm - aa + 1)
        j0 = np.where(use_lower, 0.0, aa)
        counts = np.where(use_lower, aa, mm - aa + 1).astype(int)
        kmax = int(counts.max()) if counts.size else 0
        K = np.arange(kmax)[None, :]
        valid = K < counts[:, None]
        j = j0[:, None] + K
        # log pmf at the first term of each tail
        lp0 = (gammaln(mm + 1) - gammaln(j0 + 1) - gammaln(mm - j0 + 1)
               + betaln(j0 + aal, mm - j0 + bbe) - betaln(aal, bbe))
        # log ratio from term k to term k+1, for steps that stay inside the support
        step_ok = valid & (K + 1 < counts[:, None])
        jj = np.where(step_ok, j, 0.0)
        mc = mm[:, None]
        ac = aal[:, None]
        bc = bbe[:, None]
        delta = np.where(step_ok,
                         np.log(np.where(step_ok, mc - jj, 1.0)) - np.log(jj + 1)
                         + np.log(jj + ac) - np.log(np.where(step_ok, mc - jj + bc - 1, 1.0)),
                         0.0)
        logpmf = lp0[:, None] + np.concatenate(
            [np.zeros((delta.shape[0], 1)), np.cumsum(delta, axis=1)[:, :-1]], axis=1)
        tail = np.where(valid, np.exp(np.where(valid, logpmf, 0.0)), 0.0).sum(axis=1)
        out[sl] = np.where(use_lower, 1.0 - tail, tail)
    return np.clip(out, 0.0, 1.0).reshape(np.asarray(a).shape if np.ndim(a) else ())


def bayes_p_up(xC, nC, xT, nT):
    xC, nC, xT, nT = (np.asarray(a, dtype=float) for a in (xC, nC, xT, nT))
    shape = xC.shape
    aC = (xC + 1).ravel()
    bC = (nC - xC + 1).ravel()
    aT = (xT + 1).ravel()
    bT = (nT - xT + 1).ravel()
    m = (nC + 1).ravel()            # = aC + bC - 1
    return betabinom_sf_ge(aC, m, aT, bT).reshape(shape)


_fisher_cache = {}


def fisher_p(xC, nC, xT, nT):
    """Two-sided Fisher exact p-value. Results are cached by count tuple."""
    out = np.empty(len(xC))
    for i, key in enumerate(zip(xC.astype(int), nC.astype(int), xT.astype(int), nT.astype(int))):
        if key not in _fisher_cache:
            c, nc, t, nt = key
            _fisher_cache[key] = fisher_exact([[t, nt - t], [c, nc - c]], alternative="two-sided")[1]
        out[i] = _fisher_cache[key]
    return out


def z_crit(alpha):
    return norm.ppf(1 - alpha / 2)


def first_stop(fire_pos, fire_neg):
    """Index of the first look that fires, the direction, and whether any look fired."""
    fire = fire_pos | fire_neg
    fired = fire.any(axis=1)
    k = np.argmax(fire, axis=1)
    rows = np.arange(fire.shape[0])
    sign = np.where(fire_pos[rows, k], 1, -1)
    return fired, k, sign
