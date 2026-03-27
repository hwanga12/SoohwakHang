#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/agribot_env.sh"

BACKEND_DIR="${REPO_ROOT}/backend"
PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "Backend venv not found: ${PYTHON_BIN}" >&2
    echo "Create it first with: python3 -m venv ${BACKEND_DIR}/.venv" >&2
    exit 1
fi

"${PYTHON_BIN}" -m pip install --upgrade pip
"${PYTHON_BIN}" -m pip install \
    numpy==1.26.4 \
    PyYAML \
    requests \
    scipy \
    psutil \
    polars \
    matplotlib \
    pillow \
    opencv-python \
    setuptools \
    jinja2 \
    typeguard
"${PYTHON_BIN}" -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
"${PYTHON_BIN}" -m pip install --no-deps -r "${BACKEND_DIR}/requirements.txt"
"${PYTHON_BIN}" -m pip install --no-deps ultralytics-thop==2.0.18

echo "Backend + perception runtime dependencies are installed in ${BACKEND_DIR}/.venv"
