#!/usr/bin/env bash
# Download the Criteo Uplift Modeling Dataset v2.1 (research uplift v2.1).
# Source: https://huggingface.co/datasets/criteo/criteo-uplift
# Citation: Diemert, Betlei, Renaudin, Amini (2018), KDD AdKDD/TargetAd workshop.
# License: CC BY-NC-SA 4.0 (non-commercial use only; see DESIGN.md section 2.3).
#
# The raw file is written to data/raw/, which is git-ignored and never committed.
# The download is accepted only if its SHA-256 matches the value recorded below.
# If a valid copy is already present, the script does nothing.

set -euo pipefail

URL="https://huggingface.co/datasets/criteo/criteo-uplift/resolve/main/criteo-research-uplift-v2.1.csv.gz"
FILENAME="criteo-research-uplift-v2.1.csv.gz"
EXPECTED_SHA256="2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc"
EXPECTED_BYTES="311422618"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAW_DIR="${HERE}/raw"
TARGET="${RAW_DIR}/${FILENAME}"
PARTIAL="${TARGET}.partial"

mkdir -p "${RAW_DIR}"

sha256_of() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    sha256sum "$1" | awk '{print $1}'
  fi
}

file_bytes() {
  # macOS stat uses -f, GNU stat uses -c
  stat -f %z "$1" 2>/dev/null || stat -c %s "$1"
}

if [[ -f "${TARGET}" ]]; then
  if [[ "$(file_bytes "${TARGET}")" == "${EXPECTED_BYTES}" ]] && \
     [[ "$(sha256_of "${TARGET}")" == "${EXPECTED_SHA256}" ]]; then
    echo "Already present and verified: ${TARGET}"
    exit 0
  fi
  echo "Existing file failed verification. Re-downloading." >&2
  rm -f "${TARGET}"
fi

echo "Downloading ${URL}"
curl --fail --location --retry 3 --output "${PARTIAL}" "${URL}"

ACTUAL_BYTES="$(file_bytes "${PARTIAL}")"
if [[ "${ACTUAL_BYTES}" != "${EXPECTED_BYTES}" ]]; then
  echo "Size mismatch: expected ${EXPECTED_BYTES} bytes, got ${ACTUAL_BYTES}." >&2
  rm -f "${PARTIAL}"
  exit 1
fi

ACTUAL_SHA="$(sha256_of "${PARTIAL}")"
if [[ "${ACTUAL_SHA}" != "${EXPECTED_SHA256}" ]]; then
  echo "SHA-256 mismatch: expected ${EXPECTED_SHA256}, got ${ACTUAL_SHA}." >&2
  rm -f "${PARTIAL}"
  exit 1
fi

gzip -t "${PARTIAL}"
mv "${PARTIAL}" "${TARGET}"
echo "Verified (size, SHA-256, gzip integrity): ${TARGET}"
