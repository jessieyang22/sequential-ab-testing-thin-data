"""
Shared constants and helpers for the sequential A/B testing study.

Every script in src/ imports this file. Nothing here reads the data itself,
except through the cache files that c1_pipeline.py writes into data/raw/cache/.
All constants below are the ones fixed in DESIGN.md.
"""

import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RAW_DIR = os.path.join(REPO, "data", "raw")
RAW = os.path.join(RAW_DIR, "criteo-research-uplift-v2.1.csv.gz")
CACHE = os.path.join(RAW_DIR, "cache")          # git-ignored; never committed
RESULTS = os.path.join(REPO, "results")
FIGURES = os.path.join(REPO, "figures")

FEATURES = [f"f{i}" for i in range(12)]
N_ROWS = 13979592
SEED = 20261029            # DESIGN.md 3.1 and 3.5
DEV_FRAC = 0.20            # DESIGN.md 3.1
ALPHA = 0.05               # DESIGN.md 3.5
R = 2000                   # repetitions per cell, DESIGN.md 3.5
BLOCK = 10                 # simulation step in users per arm (gcd of all look schedules)
NS = [2000, 5000, 10000, 25000, 50000]
SCENARIOS = [("A", 0.0), ("M0.25", 0.25), ("M0.5", 0.5), ("M1.0", 1.0)]
OUTCOMES = ["conversion", "visit"]
# Label written into every simulated results file (DESIGN.md 3.2, README section 2).
DATA_SOURCE = "resampled real held-out rows (Criteo uplift v2.1); simulated, not synthetic data"
Z975 = 1.959963984540054   # two-sided 95% normal quantile
ALLOCATION_TREATED_SHARE = 0.85


def cell_list():
    """All (outcome, scenario, n) cells in a fixed order.

    The index of a cell in this list plus SEED is the resampling seed
    recorded in every results file (DESIGN.md 3.5).
    """
    cells = []
    for outcome in OUTCOMES:
        for name, p in SCENARIOS:
            for n in NS:
                cells.append({"outcome": outcome, "scenario": name, "p": p, "n": n})
    for i, c in enumerate(cells):
        c["cell_index"] = i
        c["seed"] = SEED + i
    return cells


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, default=float)


def read_json(path):
    with open(path) as fh:
        return json.load(fh)


def git_note():
    """The project is not a git repository and nothing has been committed."""
    return "not a git repository; no commit made (DESIGN.md section 12)"


def load_pools():
    """Aggregate counts of the held-out partition H, written by c1_pipeline.py.

    Returns {outcome: {"N0", "K0", "N1", "K1"}} where 0 = control and 1 = treated.
    These are counts only. No row-level data is read here.
    """
    c1 = read_json(os.path.join(RESULTS, "c1_pipeline.json"))
    return c1["pools_H"]


def rates_from_pools(pools, outcome):
    pl = pools[outcome]
    return pl["K0"] / pl["N0"], pl["K1"] / pl["N1"]


def wilson(k, n):
    """95% Wilson interval for a proportion k/n (Monte Carlo error bar)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + Z975 ** 2 / n
    centre = (p + Z975 ** 2 / (2 * n)) / denom
    half = Z975 * np.sqrt(p * (1 - p) / n + Z975 ** 2 / (4 * n * n)) / denom
    return (centre - half, centre + half)
