#!/usr/bin/env bash

# 이 스크립트는 백엔드 런타임 의존성을 설치하기 위해 사용하는 실행용 쉘 스크립트다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/agribot_env.sh"

BACKEND_DIR="${REPO_ROOT}/backend"
PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python"

# 실행에 필요한 바이너리나 가상환경이 준비되지 않았으면 바로 중단해 뒤늦은 실패를 막는다.
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
