"""
Profile the raw Criteo Uplift file (v2.1) and write observed facts to results/.

What this script does, in plain terms:
1. Checks that the raw file in data/raw/ exists and matches the recorded SHA-256.
2. Reads the gzipped CSV in chunks, so the whole file never has to fit in memory.
3. Counts rows, counts missing values in every column, and records min and max
   for every numeric column.
4. Counts users and outcomes by treatment arm (the descriptive counts in DESIGN.md 2.4).
5. Computes the sizes of the development and held-out partitions defined in
   DESIGN.md 3.1 (sizes only; no row-level output is written).
6. Writes results/data_profile.json. DATA.md is written from that file.

Nothing here compares arms for a result. It only describes the file.

Run from the repository root:  python3 src/data_profile.py
"""

import gzip
import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RAW = os.path.join(REPO, "data", "raw", "criteo-research-uplift-v2.1.csv.gz")
OUT = os.path.join(REPO, "results", "data_profile.json")

EXPECTED_SHA256 = "2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc"
EXPECTED_ROWS = 13979592
EXPECTED_COLUMNS = ["f0", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11",
                    "treatment", "conversion", "visit", "exposure"]
SEED = 20261029
DEV_FRACTION = 0.20
CHUNK = 1_000_000


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def git_commit():
    try:
        out = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return "not a git repository at time of run"


def main():
    if not os.path.exists(RAW):
        sys.exit(f"Missing raw file: {RAW}. Run data/download.sh first.")

    digest = sha256_of(RAW)
    if digest != EXPECTED_SHA256:
        sys.exit(f"SHA-256 mismatch on {RAW}: {digest}")

    # Read header to confirm column order before streaming.
    with gzip.open(RAW, "rt") as fh:
        header = fh.readline().rstrip("\n").split(",")
    if header != EXPECTED_COLUMNS:
        sys.exit(f"Unexpected header: {header}")

    n_rows = 0
    missing = {c: 0 for c in EXPECTED_COLUMNS}
    mins = {c: math.inf for c in EXPECTED_COLUMNS}
    maxs = {c: -math.inf for c in EXPECTED_COLUMNS}
    counts = {"treated_users": 0, "control_users": 0,
              "treated_conv": 0, "control_conv": 0,
              "treated_visit": 0, "control_visit": 0,
              "treated_exposed": 0, "control_exposed": 0,
              "control_exposure_nonzero": 0,
              "conversion_without_visit": 0,
              "treatment_values": set(), "conversion_values": set(),
              "visit_values": set(), "exposure_values": set()}

    reader = pd.read_csv(RAW, compression="gzip", chunksize=CHUNK, dtype=float)
    for chunk in reader:
        n_rows += len(chunk)
        for c in EXPECTED_COLUMNS:
            col = chunk[c]
            missing[c] += int(col.isna().sum())
            mins[c] = min(mins[c], float(col.min()))
            maxs[c] = max(maxs[c], float(col.max()))

        t = chunk["treatment"] == 1
        k = chunk["treatment"] == 0
        counts["treated_users"] += int(t.sum())
        counts["control_users"] += int(k.sum())
        counts["treated_conv"] += int(chunk.loc[t, "conversion"].sum())
        counts["control_conv"] += int(chunk.loc[k, "conversion"].sum())
        counts["treated_visit"] += int(chunk.loc[t, "visit"].sum())
        counts["control_visit"] += int(chunk.loc[k, "visit"].sum())
        counts["treated_exposed"] += int(chunk.loc[t, "exposure"].sum())
        counts["control_exposed"] += int(chunk.loc[k, "exposure"].sum())
        counts["control_exposure_nonzero"] += int((chunk.loc[k, "exposure"] != 0).sum())
        counts["conversion_without_visit"] += int(((chunk["conversion"] == 1) & (chunk["visit"] == 0)).sum())
        for c_name, key in [("treatment", "treatment_values"), ("conversion", "conversion_values"),
                            ("visit", "visit_values"), ("exposure", "exposure_values")]:
            counts[key].update(chunk[c_name].dropna().unique().tolist())

    if n_rows != EXPECTED_ROWS:
        sys.exit(f"Row count {n_rows} does not match expected {EXPECTED_ROWS}")

    dev_rows = int(math.floor(DEV_FRACTION * n_rows))
    held_rows = n_rows - dev_rows

    total_users = counts["treated_users"] + counts["control_users"]
    result = {
        "script": "src/data_profile.py",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "seed": SEED,
        "file": os.path.relpath(RAW, REPO),
        "file_bytes": os.path.getsize(RAW),
        "sha256": digest,
        "rows": n_rows,
        "columns": EXPECTED_COLUMNS,
        "date_columns": [],
        "date_range": "none: the file has no timestamp or date column",
        "missing_by_column": missing,
        "min_by_column": mins,
        "max_by_column": maxs,
        "treated_users": counts["treated_users"],
        "control_users": counts["control_users"],
        "treated_share": counts["treated_users"] / total_users,
        "control_conversions": counts["control_conv"],
        "treated_conversions": counts["treated_conv"],
        "control_conversion_rate": counts["control_conv"] / counts["control_users"],
        "treated_conversion_rate": counts["treated_conv"] / counts["treated_users"],
        "control_visit_rate": counts["control_visit"] / counts["control_users"],
        "treated_visit_rate": counts["treated_visit"] / counts["treated_users"],
        "treated_visits": counts["treated_visit"],
        "control_visits": counts["control_visit"],
        "treated_exposed_count": counts["treated_exposed"],
        "treated_exposed_share": counts["treated_exposed"] / counts["treated_users"],
        "control_exposed_count": counts["control_exposed"],
        "control_exposure_nonzero_count": counts["control_exposure_nonzero"],
        "conversion_without_visit_count": counts["conversion_without_visit"],
        "distinct_values": {
            "treatment": sorted(counts["treatment_values"]),
            "conversion": sorted(counts["conversion_values"]),
            "visit": sorted(counts["visit_values"]),
            "exposure": sorted(counts["exposure_values"]),
        },
        "partition_seed": SEED,
        "partition_dev_rows": dev_rows,
        "partition_held_rows": held_rows,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=2, default=float)
    print(json.dumps(result, indent=2, default=float))


if __name__ == "__main__":
    main()
