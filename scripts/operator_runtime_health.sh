#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/agribot_env.sh"

AGRIBOT_WS_DEFAULT="${AGRIBOT_WS}"
DEFAULT_RUNTIME_DIR="/tmp/agribot_runtime"

EXPECTED_RUNTIME_DIR="${AGRIBOT_RUNTIME_DIR:-${DEFAULT_RUNTIME_DIR}}"
EXPECTED_GRAPHICS_PROFILE="${AGRIBOT_GRAPHICS_PROFILE:-auto}"
BACKEND_URL="${BACKEND_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}}"
FRONTEND_URL="${FRONTEND_URL:-http://${FRONTEND_HOST}:${FRONTEND_PORT}}"
ROS_DISTRO_VALUE="${ROS_DISTRO}"
MODE="check"

FAIL_COUNT=0
WARN_COUNT=0

usage() {
    cat <<'EOF'
Usage: operator_runtime_health.sh [options]

Options:
  --print-env               Print shared export lines for the current repo.
  --reset-runtime           Recreate the expected runtime directory.
  --runtime-dir <path>      Override the expected runtime directory.
  --backend-url <url>       Override backend base URL. Default: http://127.0.0.1:8000
  --frontend-url <url>      Override frontend base URL. Default: http://127.0.0.1:5173
  -h, --help                Show this help.

Examples:
  source <(./scripts/operator_runtime_health.sh --print-env)
  ./scripts/operator_runtime_health.sh --reset-runtime
  ./scripts/operator_runtime_health.sh
EOF
}

section() {
    printf '\n== %s ==\n' "$1"
}

ok() {
    printf '[ok] %s\n' "$1"
}

warn() {
    WARN_COUNT=$((WARN_COUNT + 1))
    printf '[warn] %s\n' "$1"
}

fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf '[fail] %s\n' "$1"
}

note() {
    printf ' - %s\n' "$1"
}

extract_port() {
    local url="$1"
    local host_port="${url#*://}"
    host_port="${host_port%%/*}"

    if [[ "${host_port}" == *:* ]]; then
        printf '%s\n' "${host_port##*:}"
        return
    fi

    if [[ "${url}" == https://* ]]; then
        printf '443\n'
        return
    fi

    printf '80\n'
}

print_env() {
    cat <<EOF
export REPO_ROOT="${REPO_ROOT}"
export AGRIBOT_WS="${AGRIBOT_WS_DEFAULT}"
export ROS_DISTRO="${ROS_DISTRO_VALUE}"
export AGRIBOT_RUNTIME_DIR="${EXPECTED_RUNTIME_DIR}"
export AGRIBOT_GRAPHICS_PROFILE="${EXPECTED_GRAPHICS_PROFILE}"
EOF
}

reset_runtime_dir() {
    rm -rf "${EXPECTED_RUNTIME_DIR}"
    mkdir -p "${EXPECTED_RUNTIME_DIR}"
    printf 'reset runtime dir: %s\n' "${EXPECTED_RUNTIME_DIR}"
}

read_process_env_value() {
    local pid="$1"
    local key="$2"

    if [[ ! -r "/proc/${pid}/environ" ]]; then
        return
    fi

    tr '\0' '\n' <"/proc/${pid}/environ" | sed -n "s/^${key}=//p" | head -n 1
}

read_process_runtime_dir() {
    local pid="$1"
    read_process_env_value "${pid}" "AGRIBOT_RUNTIME_DIR"
}

read_process_graphics_profile() {
    local pid="$1"
    read_process_env_value "${pid}" "AGRIBOT_GRAPHICS_PROFILE"
}

read_process_cmdline() {
    local pid="$1"
    ps -p "${pid}" -o args= 2>/dev/null | sed 's/^ *//'
}

list_listen_pids() {
    local port="$1"
    lsof -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | sort -u || true
}

check_port_process() {
    local label="$1"
    local port="$2"
    local enforce_runtime="$3"
    local -a pids=()

    mapfile -t pids < <(list_listen_pids "${port}")

    if [[ ${#pids[@]} -eq 0 ]]; then
        fail "${label} port ${port} is not listening."
        return
    fi

    ok "${label} port ${port} is listening."

    for pid in "${pids[@]}"; do
        local runtime_dir=""
        local graphics_profile=""
        local cmdline=""

        runtime_dir="$(read_process_runtime_dir "${pid}")"
        graphics_profile="$(read_process_graphics_profile "${pid}")"
        cmdline="$(read_process_cmdline "${pid}")"
        note "${label} pid=${pid} runtime_dir=${runtime_dir:-<unset>} graphics_profile=${graphics_profile:-<unset>} cmd=${cmdline:-<unknown>}"

        if [[ "${enforce_runtime}" != "true" ]]; then
            continue
        fi

        if [[ -z "${runtime_dir}" ]]; then
            if [[ "${EXPECTED_RUNTIME_DIR}" == "${DEFAULT_RUNTIME_DIR}" ]]; then
                note "${label} pid ${pid} relies on the default runtime dir ${DEFAULT_RUNTIME_DIR}."
            else
                fail "${label} pid ${pid} has no AGRIBOT_RUNTIME_DIR and will likely fall back to ${DEFAULT_RUNTIME_DIR}, expected ${EXPECTED_RUNTIME_DIR}."
            fi
        elif [[ "${runtime_dir}" != "${EXPECTED_RUNTIME_DIR}" ]]; then
            fail "${label} pid ${pid} uses ${runtime_dir}, expected ${EXPECTED_RUNTIME_DIR}."
        else
            ok "${label} pid ${pid} uses the expected runtime directory."
        fi

        if [[ -n "${graphics_profile}" && "${graphics_profile}" != "${EXPECTED_GRAPHICS_PROFILE}" ]]; then
            warn "${label} pid ${pid} uses graphics profile ${graphics_profile}, expected ${EXPECTED_GRAPHICS_PROFILE}."
        fi
    done
}

check_named_processes() {
    local label="$1"
    local pattern="$2"
    local -a pids=()

    mapfile -t pids < <(pgrep -f "${pattern}" | sort -u || true)

    if [[ ${#pids[@]} -eq 0 ]]; then
        fail "${label} process is not running."
        return
    fi

    ok "${label} process is running."

    for pid in "${pids[@]}"; do
        local runtime_dir=""
        local graphics_profile=""
        local cmdline=""

        runtime_dir="$(read_process_runtime_dir "${pid}")"
        graphics_profile="$(read_process_graphics_profile "${pid}")"
        cmdline="$(read_process_cmdline "${pid}")"
        note "${label} pid=${pid} runtime_dir=${runtime_dir:-<unset>} graphics_profile=${graphics_profile:-<unset>} cmd=${cmdline:-<unknown>}"

        if [[ -z "${runtime_dir}" ]]; then
            if [[ "${EXPECTED_RUNTIME_DIR}" == "${DEFAULT_RUNTIME_DIR}" ]]; then
                note "${label} pid ${pid} relies on the default runtime dir ${DEFAULT_RUNTIME_DIR}."
            else
                fail "${label} pid ${pid} has no AGRIBOT_RUNTIME_DIR and will likely fall back to ${DEFAULT_RUNTIME_DIR}, expected ${EXPECTED_RUNTIME_DIR}."
            fi
        elif [[ "${runtime_dir}" != "${EXPECTED_RUNTIME_DIR}" ]]; then
            fail "${label} pid ${pid} uses ${runtime_dir}, expected ${EXPECTED_RUNTIME_DIR}."
        fi

        if [[ -n "${graphics_profile}" && "${graphics_profile}" != "${EXPECTED_GRAPHICS_PROFILE}" ]]; then
            warn "${label} pid ${pid} uses graphics profile ${graphics_profile}, expected ${EXPECTED_GRAPHICS_PROFILE}."
        fi
    done
}

check_backend_api() {
    local control_json
    local latest_json
    local status_json
    local control_available=""
    local latest_available=""
    local pose_source=""
    local control_message=""
    local latest_message=""

    control_json="$(mktemp)"
    latest_json="$(mktemp)"
    status_json="$(mktemp)"

    curl -fsS --max-time 2 "${BACKEND_URL}/api/v1/robot/control/status" >"${control_json}" || {
        fail "backend control status API is unreachable: ${BACKEND_URL}/api/v1/robot/control/status"
        rm -f "${control_json}" "${latest_json}" "${status_json}"
        return
    }

    curl -fsS --max-time 2 "${BACKEND_URL}/api/v1/robot/commands/latest" >"${latest_json}" || {
        fail "backend latest command API is unreachable: ${BACKEND_URL}/api/v1/robot/commands/latest"
        rm -f "${control_json}" "${latest_json}" "${status_json}"
        return
    }

    curl -fsS --max-time 2 "${BACKEND_URL}/api/v1/robot/status" >"${status_json}" || {
        fail "backend robot status API is unreachable: ${BACKEND_URL}/api/v1/robot/status"
        rm -f "${control_json}" "${latest_json}" "${status_json}"
        return
    }

    control_available="$(jq -r '.data.available // false' "${control_json}")"
    latest_available="$(jq -r '.data.available // false' "${latest_json}")"
    pose_source="$(jq -r '.data.pose_source // empty' "${status_json}")"
    control_message="$(jq -r '.data.message // empty' "${control_json}")"
    latest_message="$(jq -r '.data.message // empty' "${latest_json}")"

    if [[ "${control_available}" == "true" ]]; then
        ok "backend sees robot_control_state.json."
    else
        fail "backend does not see robot_control_state.json. ${control_message}"
    fi

    if [[ "${latest_available}" == "true" ]]; then
        ok "backend sees robot_manual_command_status.json."
    else
        fail "backend does not see robot_manual_command_status.json. ${latest_message}"
    fi

    if [[ -n "${pose_source}" ]]; then
        note "backend robot status pose_source=${pose_source}"
    fi

    rm -f "${control_json}" "${latest_json}" "${status_json}"
}

check_ros_nodes() {
    local ros2_output
    local ros2_error
    local rc=0
    local attempt=1
    local max_attempts=3
    local all_required_present=0
    local -a required_nodes=(
        "robot_manual_command_executor"
        "mission_bridge_executor"
        "patrol_node"
        "harvest_route_node"
    )

    ros2_output="$(mktemp)"
    ros2_error="$(mktemp)"

    if ! source_ros_setup_files >"${ros2_error}" 2>&1; then
        fail "failed to source ROS setup files before ros2 node list."
        if [[ -s "${ros2_error}" ]]; then
            note "ros2 error: $(tr '\n' ' ' <"${ros2_error}" | sed 's/  */ /g')"
        fi
        rm -f "${ros2_output}" "${ros2_error}"
        return
    fi

    while (( attempt <= max_attempts )); do
        : >"${ros2_output}"
        : >"${ros2_error}"
        rc=0

        if command -v timeout >/dev/null 2>&1; then
            timeout 5 ros2 node list >"${ros2_output}" 2>"${ros2_error}" || rc=$?
        else
            ros2 node list >"${ros2_output}" 2>"${ros2_error}" || rc=$?
        fi

        if [[ ${rc} -ne 0 ]]; then
            if (( attempt == max_attempts )); then
                fail "ros2 node list failed. Source /opt/ros/${ROS_DISTRO_VALUE}/setup.bash and ${AGRIBOT_WS_DEFAULT}/install/setup.bash first."
                if [[ -s "${ros2_error}" ]]; then
                    note "ros2 error: $(tr '\n' ' ' <"${ros2_error}" | sed 's/  */ /g')"
                fi
                rm -f "${ros2_output}" "${ros2_error}"
                return
            fi
            sleep 1
            attempt=$((attempt + 1))
            continue
        fi

        all_required_present=1
        for node_name in "${required_nodes[@]}"; do
            if ! grep -Eq "(^|/)${node_name}$" "${ros2_output}"; then
                all_required_present=0
                break
            fi
        done

        if (( all_required_present )); then
            break
        fi

        if (( attempt < max_attempts )); then
            sleep 1
        fi
        attempt=$((attempt + 1))
    done

    if [[ ! -s "${ros2_output}" ]]; then
        fail "ros2 node list is empty."
    else
        ok "ros2 node list returned at least one node."
    fi

    for node_name in "${required_nodes[@]}"; do
        if grep -Eq "(^|/)${node_name}$" "${ros2_output}"; then
            ok "required ROS node detected: ${node_name}"
        else
            fail "required ROS node missing: ${node_name}"
        fi
    done

    rm -f "${ros2_output}" "${ros2_error}"
}

check_runtime_dir_files() {
    local runtime_dir="$1"
    local label="$2"
    local -a files=()

    if [[ ! -d "${runtime_dir}" ]]; then
        note "${label}: directory missing (${runtime_dir})"
        return
    fi

    mapfile -t files < <(
        find "${runtime_dir}" -maxdepth 2 -type f \
            \( \
                -name 'robot_*.json' \
                -o -name 'harvest_*.json' \
                -o -path "${runtime_dir}/mission_statuses/*.json" \
                -o -path "${runtime_dir}/harvest_events/*.json" \
                -o -path "${runtime_dir}/harvest_action_statuses/*.json" \
            \) \
            | sort
    )

    if [[ ${#files[@]} -eq 0 ]]; then
        note "${label}: no runtime files in ${runtime_dir}"
        return
    fi

    note "${label}: ${#files[@]} runtime file(s) in ${runtime_dir}"
    for file_path in "${files[@]}"; do
        note "${label} file: ${file_path}"
    done
}

check_runtime_files() {
    local command_request="${EXPECTED_RUNTIME_DIR}/robot_manual_command.json"
    local command_status="${EXPECTED_RUNTIME_DIR}/robot_manual_command_status.json"
    local control_state="${EXPECTED_RUNTIME_DIR}/robot_control_state.json"
    local mission_request="${EXPECTED_RUNTIME_DIR}/robot_mission_request.json"
    local mission_status="${EXPECTED_RUNTIME_DIR}/robot_mission_status.json"
    local mission_status_dir="${EXPECTED_RUNTIME_DIR}/mission_statuses"
    local repo_root_control="${REPO_ROOT}/robot_control_state.json"
    local repo_root_pose="${REPO_ROOT}/robot_pose_snapshot.json"
    local repo_root_layers="${REPO_ROOT}/robot_map_layers_snapshot.json"
    local mission_status_count=0

    if [[ ! -d "${EXPECTED_RUNTIME_DIR}" ]]; then
        fail "expected runtime directory is missing: ${EXPECTED_RUNTIME_DIR}"
        return
    fi

    ok "expected runtime directory exists: ${EXPECTED_RUNTIME_DIR}"
    check_runtime_dir_files "${EXPECTED_RUNTIME_DIR}" "expected"

    if [[ -d "${mission_status_dir}" ]]; then
        mission_status_count="$(find "${mission_status_dir}" -maxdepth 1 -type f -name '*.json' | wc -l | tr -d ' ')"
    fi

    if [[ -f "${command_request}" && ! -f "${command_status}" ]]; then
        fail "robot_manual_command.json exists but robot_manual_command_status.json is missing."
    fi

    if [[ -f "${mission_request}" && ! -f "${mission_status}" && "${mission_status_count}" == "0" ]]; then
        fail "robot_mission_request.json exists but mission status files are missing."
    fi

    if [[ ! -f "${control_state}" ]]; then
        fail "robot_control_state.json is missing from ${EXPECTED_RUNTIME_DIR}."
    fi

    if [[ "${EXPECTED_RUNTIME_DIR}" != "${REPO_ROOT}" ]]; then
        if [[ -f "${repo_root_control}" || -f "${repo_root_pose}" || -f "${repo_root_layers}" ]]; then
            check_runtime_dir_files "${REPO_ROOT}" "repo-root candidate"
            if [[ ! -f "${control_state}" && -f "${repo_root_control}" ]]; then
                fail "repo root has robot_control_state.json while expected runtime dir does not. Likely runtime dir mismatch between backend and ROS."
            fi
        fi
    fi

    if [[ "${EXPECTED_RUNTIME_DIR}" != "${DEFAULT_RUNTIME_DIR}" && -d "${DEFAULT_RUNTIME_DIR}" ]]; then
        check_runtime_dir_files "${DEFAULT_RUNTIME_DIR}" "default candidate"
    fi
}

print_summary() {
    section "Summary"
    note "expected AGRIBOT_RUNTIME_DIR=${EXPECTED_RUNTIME_DIR}"
    note "expected AGRIBOT_GRAPHICS_PROFILE=${EXPECTED_GRAPHICS_PROFILE}"
    note "backend URL=${BACKEND_URL}"
    note "frontend URL=${FRONTEND_URL}"

    if [[ ${FAIL_COUNT} -eq 0 && ${WARN_COUNT} -eq 0 ]]; then
        ok "All runtime checks passed."
        return
    fi

    if [[ ${FAIL_COUNT} -gt 0 ]]; then
        printf '[fail] Detected %s blocking issue(s).\n' "${FAIL_COUNT}"
        note "In this state, accepted request files may be written but the 7 operator actions will not complete end-to-end."
    fi

    if [[ ${WARN_COUNT} -gt 0 ]]; then
        printf '[warn] Detected %s warning(s).\n' "${WARN_COUNT}"
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --print-env)
            MODE="print-env"
            shift
            ;;
        --reset-runtime)
            MODE="reset-runtime"
            shift
            ;;
        --runtime-dir)
            if [[ $# -lt 2 ]]; then
                echo "--runtime-dir requires a value." >&2
                exit 2
            fi
            EXPECTED_RUNTIME_DIR="$2"
            shift 2
            ;;
        --backend-url)
            if [[ $# -lt 2 ]]; then
                echo "--backend-url requires a value." >&2
                exit 2
            fi
            BACKEND_URL="$2"
            shift 2
            ;;
        --frontend-url)
            if [[ $# -lt 2 ]]; then
                echo "--frontend-url requires a value." >&2
                exit 2
            fi
            FRONTEND_URL="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

case "${MODE}" in
    print-env)
        print_env
        exit 0
        ;;
    reset-runtime)
        reset_runtime_dir
        exit 0
        ;;
esac

section "Shell Environment"
note "repo_root=${REPO_ROOT}"
note "agribot_ws=${AGRIBOT_WS_DEFAULT}"
note "ros_distro=${ROS_DISTRO_VALUE}"
note "expected_runtime_dir=${EXPECTED_RUNTIME_DIR}"
note "expected_graphics_profile=${EXPECTED_GRAPHICS_PROFILE}"

section "Ports And Processes"
check_port_process "backend" "$(extract_port "${BACKEND_URL}")" "true"
check_port_process "frontend" "$(extract_port "${FRONTEND_URL}")" "false"
check_named_processes "runtime_snapshot_exporter" "runtime_snapshot_exporter"
check_named_processes "robot_manual_command_executor" "robot_manual_command_executor"
check_named_processes "mission_bridge_executor" "mission_bridge_executor"
check_named_processes "patrol_node" "patrol_node"
check_named_processes "harvest_route_node" "harvest_route_node"

section "Backend API"
check_backend_api

section "ROS Nodes"
check_ros_nodes

section "Runtime Files"
check_runtime_files

print_summary

if [[ ${FAIL_COUNT} -gt 0 ]]; then
    exit 1
fi
