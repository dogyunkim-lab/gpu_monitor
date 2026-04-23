#!/bin/bash
# GPU Monitor 설치 스크립트 (RHEL 8 / 폐쇄망)
# Prometheus + Grafana 설정 생성 → 배포 → 서비스 재시작
# 사용법: cd gpu-monitor && bash scripts/install.sh

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="${PROJECT_DIR}/src"
VENV_DIR="${PROJECT_DIR}/venv"
CONFIG_PATH="${PROJECT_DIR}/config.yaml"
OUTPUT_DIR="${PROJECT_DIR}/output"

PROMETHEUS_CONF_DIR="/etc/prometheus"
GRAFANA_CONF_DIR="/etc/grafana"

echo "========================================="
echo "  GPU Monitor — Prometheus + Grafana 설정 배포"
echo "========================================="
echo "  프로젝트 경로: ${PROJECT_DIR}"

# 1. Python venv 생성
echo "[1/5] Python venv 생성: ${VENV_DIR}"
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

# 2. 의존성 설치
echo "[2/5] 의존성 설치"
pip install --upgrade pip
cd "${SRC_DIR}"
pip install -e .

# 3. 설정 파일 확인
echo "[3/5] 설정 파일 확인"
if [ ! -f "${CONFIG_PATH}" ]; then
    cp "${PROJECT_DIR}/examples/config.yaml.example" "${CONFIG_PATH}"
    echo "  config.yaml 생성됨 — VM 목록을 편집하세요: ${CONFIG_PATH}"
    echo "  편집 후 다시 실행하세요."
    deactivate
    exit 0
fi

# 4. 설정 파일 생성
echo "[4/5] Prometheus + Grafana 설정 생성"
gpu-monitor -c "${CONFIG_PATH}" generate all -o "${OUTPUT_DIR}"

# 5. 설정 배포 + 서비스 재시작
echo "[5/5] 설정 배포"

# Prometheus
if [ -d "${OUTPUT_DIR}/prometheus" ]; then
    echo "  Prometheus 설정 → ${PROMETHEUS_CONF_DIR}"
    sudo cp "${OUTPUT_DIR}/prometheus/prometheus.yml" "${PROMETHEUS_CONF_DIR}/prometheus.yml"
    sudo mkdir -p "${PROMETHEUS_CONF_DIR}/rules"
    sudo cp "${OUTPUT_DIR}/prometheus/rules/gpu_alerts.yml" "${PROMETHEUS_CONF_DIR}/rules/gpu_alerts.yml"

    if systemctl is-active --quiet prometheus; then
        echo "  Prometheus 재시작"
        sudo systemctl reload prometheus || sudo systemctl restart prometheus
    else
        echo "  [WARN] Prometheus 서비스가 실행중이지 않습니다."
    fi
fi

# Grafana
if [ -d "${OUTPUT_DIR}/grafana" ]; then
    echo "  Grafana 설정 → ${GRAFANA_CONF_DIR}"
    sudo mkdir -p "${GRAFANA_CONF_DIR}/provisioning/datasources"
    sudo mkdir -p "${GRAFANA_CONF_DIR}/provisioning/dashboards"
    sudo mkdir -p "${GRAFANA_CONF_DIR}/dashboards"

    sudo cp "${OUTPUT_DIR}/grafana/provisioning/datasources/prometheus.yml" \
        "${GRAFANA_CONF_DIR}/provisioning/datasources/prometheus.yml"
    sudo cp "${OUTPUT_DIR}/grafana/provisioning/dashboards/default.yml" \
        "${GRAFANA_CONF_DIR}/provisioning/dashboards/default.yml"
    # 모든 대시보드 JSON 복사 (gpu-cluster.json + vllm-monitor.json)
    sudo cp "${OUTPUT_DIR}"/grafana/dashboards/*.json \
        "${GRAFANA_CONF_DIR}/dashboards/"

    if systemctl is-active --quiet grafana-server; then
        echo "  Grafana 재시작"
        sudo systemctl restart grafana-server
    else
        echo "  [WARN] Grafana 서비스가 실행중이지 않습니다."
    fi
fi

deactivate

echo ""
echo "========================================="
echo "  배포 완료!"
echo "========================================="
echo ""
echo "다음 단계:"
echo "  1. VM 목록 확인: ${VENV_DIR}/bin/gpu-monitor -c ${CONFIG_PATH} status"
echo "  2. 연결 검증:    ${VENV_DIR}/bin/gpu-monitor -c ${CONFIG_PATH} validate"
echo "  3. Prometheus:   http://<이 서버 IP>:9090/targets"
echo "  4. Grafana:      http://<이 서버 IP>:3000"
