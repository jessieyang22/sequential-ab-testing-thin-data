"""
Provenance record for every file in results/ (DESIGN.md section 8).

This script was added after the first run, and it was rewritten on 2026-10-30 after a review.
The first version gave the simulation fields (R, n grid, seed) to every file, including files
that use no simulation, and it did not map some producers. Now:
- every results file must have a producer in PRODUCER (the script raises an error otherwise);
- files that use no simulation record "not applicable" for R, n grid and seed;
- dates are file modification times on disk, not the time written inside the producing script.

Writes results/provenance.json. Run it last, after every other script, because it records
file times.
"""

import datetime
import glob
import os
import sys

from common import CACHE, DATA_SOURCE, NS, R, RESULTS, SEED, git_note, write_json

SIM_LABEL = DATA_SOURCE
NOT_SIM = "no simulation in this file (closed-form, counts, or full-pool regression)"

# Producing script for each results file (the write calls in src/ and the console logs
# written by the commands in README section 3).
PRODUCER = {
    "data_profile.json": "src/data_profile.py",
    "c1_balance.csv": "src/c1_pipeline.py",
    "c1_pipeline.json": "src/c1_pipeline.py",
    "c2_sample_size.csv": "src/c2_power.py",
    "c2_power_check.json": "src/c2_power.py",
    "python_boundaries.csv": "src/c3_boundaries.py",
    "v3_boundary_check.json": "src/c3_boundaries.py",
    "gsdesign_boundaries.csv": "src/c3_validate_R.R",
    "primary_grid.csv": "src/c5_score.py",
    "checks_V2_V4.json": "src/c5_score.py",
    "robust_R1_visit_grid.csv": "src/c6_robustness.py",
    "robust_R3_schedule_alpha.csv": "src/c6_robustness.py",
    "robust_R4_cuped.csv": "src/c6_robustness.py",
    "answers.json": "src/c8_answers.py",
    "debug/engine_check_D.json": "src/c4_engine.py",
    "debug/unit_tests.txt": "src/c3_unit_tests.py",
    "debug/c3_unit_tests.log": "src/c3_unit_tests.py (console log)",
    "debug/c3_validate_R.log": "src/c3_validate_R.R (console log)",
    "debug/v3_run.log": "src/c3_boundaries.py (console log)",
    "debug/c5_run.log": "src/c5_score.py (console log)",
    "debug/c6_R1.log": "src/c6_robustness.py R1 (console log)",
    "debug/c6_R3.log": "src/c6_robustness.py R3 (console log)",
    "debug/c6_R4.log": "src/c6_robustness.py R4 (console log)",
    "debug/c8.log": "src/c8_answers.py (console log)",
    "debug/c10_sensitivity.log": "src/c10_sensitivity.py all (console log)",
    "sensitivity_S1_M5_tau2.csv": "src/c10_sensitivity.py S1 (post hoc, DESIGN.md 13.4)",
    "sensitivity_S2_R4_diagnostic_M1.0_n50000.json": "src/c10_sensitivity.py S2 (post hoc, DESIGN.md 13.4)",
    "sensitivity_S2_R4_diagnostic_A_n50000.json": "src/c10_sensitivity.py S2 (post hoc, DESIGN.md 13.4)",
    "sensitivity_S3_full_H_ols.json": "src/c10_sensitivity.py S3 (post hoc, DESIGN.md 13.4)",
    "sensitivity_S4_M6_matched_alpha.csv": "src/c10_sensitivity.py S4 (post hoc)",
    "sensitivity_S5_design_inputs.json": "src/c10_sensitivity.py S5 (post hoc, arithmetic)",
    "sensitivity_S6_alternative_truth.csv": "src/c10_sensitivity.py S6 (post hoc)",
}

# Files that use no simulation at all.
NO_SIMULATION = {
    "data_profile.json", "c1_balance.csv", "c1_pipeline.json", "c2_sample_size.csv",
    "python_boundaries.csv", "v3_boundary_check.json", "gsdesign_boundaries.csv",
    "debug/unit_tests.txt", "debug/c3_unit_tests.log", "debug/c3_validate_R.log",
    "debug/v3_run.log", "sensitivity_S3_full_H_ols.json", "sensitivity_S5_design_inputs.json",
}

DATA_SOURCE_OVERRIDE = {
    "data_profile.json": "descriptive counts from the full raw file (real data, not simulated)",
    "c1_balance.csv": "held-out partition H (real data, not simulated)",
    "c1_pipeline.json": "full file and held-out partition H counts (real data, not simulated)",
    "c2_sample_size.csv": "closed-form formula with control and treated rates from H counts (not simulated)",
    "python_boundaries.csv": "group-sequential boundary arithmetic (no data)",
    "v3_boundary_check.json": "group-sequential boundary arithmetic (no data)",
    "gsdesign_boundaries.csv": "group-sequential boundary arithmetic from gsDesign (no data)",
    "debug/unit_tests.txt": "unit tests on the rules and engine (no results)",
    "debug/c3_unit_tests.log": "unit tests on the rules and engine (no results)",
    "debug/c3_validate_R.log": "gsDesign boundary arithmetic (no data)",
    "debug/v3_run.log": "boundary arithmetic (no data)",
    "sensitivity_S3_full_H_ols.json": "all rows of partition H (real data, not resampled, not synthetic)",
    "sensitivity_S5_design_inputs.json": "arithmetic on the H counts, closed-form formulas and a workload count (no simulation)",
    "debug/engine_check_D.json": "development partition D, debugging only (real data, not resampled; no reported number)",
}

# Seed rule and repetition count for simulation files.
SEED_RULE = {
    "primary_grid.csv": f"SEED + cell_index ({SEED} + index in common.cell_list())",
    "checks_V2_V4.json": f"SEED + cell_index (same cells as primary_grid.csv); exact checks use no seed",
    "robust_R1_visit_grid.csv": "SEED + cell_index (cell_list order, visit outcome)",
    "robust_R3_schedule_alpha.csv": "SEED + cell_index (conversion cells, same as primary)",
    "robust_R4_cuped.csv": "per-cell seeds recorded in the file's seed column",
    "answers.json": "inherits the seeds of the files it reads",
    "sensitivity_S1_M5_tau2.csv": "SEED + cell_index (same cells as primary grid; multiplier 1 reproduces primary M5)",
    "sensitivity_S2_R4_diagnostic_M1.0_n50000.json": "SEED + 134 (same stream as R4, M(1.0), n = 50,000)",
    "sensitivity_S2_R4_diagnostic_A_n50000.json": "SEED + 104 (same stream as R4, A, n = 50,000)",
    "sensitivity_S4_M6_matched_alpha.csv": "SEED + cell_index (same cells as primary grid, Scenarios A and M(1.0))",
    "sensitivity_S6_alternative_truth.csv": f"SEED + 500 + n index (n index 0 to 4 for n = 2,000 to 50,000)",
    "c2_power_check.json": "20261089 (reserved cell index 60, DESIGN.md 13.1.12)",
    "debug/engine_check_D.json": "999 (debug only, partition D)",
}
REPS = {
    "primary_grid.csv": R,
    "checks_V2_V4.json": R,
    "robust_R1_visit_grid.csv": R,
    "robust_R3_schedule_alpha.csv": R,
    "robust_R4_cuped.csv": R,
    "c2_power_check.json": R,
    "answers.json": R,
    "debug/engine_check_D.json": 6000,
    "sensitivity_S1_M5_tau2.csv": R,
    "sensitivity_S2_R4_diagnostic_M1.0_n50000.json": 500,
    "sensitivity_S2_R4_diagnostic_A_n50000.json": 500,
    "sensitivity_S4_M6_matched_alpha.csv": R,
    "sensitivity_S6_alternative_truth.csv": R,
}
N_GRID = {
    "primary_grid.csv": NS,
    "checks_V2_V4.json": NS,
    "robust_R1_visit_grid.csv": NS,
    "robust_R3_schedule_alpha.csv": NS,
    "robust_R4_cuped.csv": NS,
    "answers.json": NS,
    "c2_power_check.json": [29630],
    "debug/engine_check_D.json": [2000],
    "sensitivity_S1_M5_tau2.csv": NS,
    "sensitivity_S2_R4_diagnostic_M1.0_n50000.json": [50000],
    "sensitivity_S2_R4_diagnostic_A_n50000.json": [50000],
    "sensitivity_S4_M6_matched_alpha.csv": NS,
    "sensitivity_S6_alternative_truth.csv": NS,
}


def main():
    entries = {}
    missing = []
    paths = sorted(glob.glob(os.path.join(RESULTS, "**", "*"), recursive=True))
    for path in paths:
        if os.path.isdir(path):
            continue
        rel = os.path.relpath(path, RESULTS)
        if rel == "provenance.json":
            continue
        if rel not in PRODUCER:
            missing.append(rel)
            continue
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path)).astimezone()
        sim = rel not in NO_SIMULATION
        entries[rel] = {
            "script": PRODUCER[rel],
            "simulation": sim,
            "data_source": DATA_SOURCE_OVERRIDE.get(rel, SIM_LABEL if sim else NOT_SIM),
            "seed": SEED_RULE.get(rel, f"SEED {SEED} (common.py)") if sim else "not applicable",
            "R": REPS.get(rel, R) if sim else "not applicable",
            "n_grid": N_GRID.get(rel, NS) if sim else "not applicable",
            "git": git_note(),
            "file_modified": mtime.isoformat(timespec="seconds"),
            "date_source": "file modification time (not written by the producing script)",
        }
    if missing:
        sys.exit("No producer in PRODUCER for: " + ", ".join(missing))
    out = {
        "script": "src/c9_provenance.py",
        "note": "Metadata added after the run to meet DESIGN.md section 8. "
                "Dates are file modification times. Files with simulation=false use no simulation.",
        "cache_dir_note": f"raw arrays in {os.path.relpath(CACHE, os.path.dirname(RESULTS))} (git-ignored)",
        "files": entries,
    }
    write_json(os.path.join(RESULTS, "provenance.json"), out)
    print("Wrote", os.path.join(RESULTS, "provenance.json"), "with", len(entries), "entries")


if __name__ == "__main__":
    main()
