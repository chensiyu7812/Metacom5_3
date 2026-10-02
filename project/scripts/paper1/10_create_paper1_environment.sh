#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PAPER1_ENV_NAME="${1:-metacom-paper1-py311}"
ENVIRONMENT_FILE="${PROJECT_DIR}/environments/paper1-py311.yml"
LOCK_FILE="${PROJECT_DIR}/environments/requirements-paper1-py311.lock.txt"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda is required to create the Paper-1 environment" >&2
  exit 2
fi

# The checked-in YAML is the single Conda bootstrap definition. `env update`
# creates a missing env and reconciles an existing one without writing the
# environment directory into the repository.
conda env update -n "${PAPER1_ENV_NAME}" -f "${ENVIRONMENT_FILE}"

# Install the driver-compatible CUDA wheel from its single-purpose index
# before resolving the project. This prevents PyPI's newest torch build from
# silently selecting a CUDA runtime newer than the research host supports.
conda run -n "${PAPER1_ENV_NAME}" env PYTHONNOUSERSITE=1 \
  python -m pip install \
  --index-url https://download.pytorch.org/whl/cu121 \
  'torch==2.3.1+cu121'

conda run -n "${PAPER1_ENV_NAME}" env PYTHONNOUSERSITE=1 \
  python -m pip install \
  --constraint "${LOCK_FILE}" \
  --editable "${PROJECT_DIR}[dev,official-rag]"

conda run -n "${PAPER1_ENV_NAME}" env PYTHONNOUSERSITE=1 \
  python -m pip check

echo "Created/reconciled ${PAPER1_ENV_NAME} from ${ENVIRONMENT_FILE}"
echo "Run the attestation script with explicit local model snapshot paths."
