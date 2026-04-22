#!/bin/bash
# GPU Monitor 설치 스크립트 (RHEL 8 / 폐쇄망)
# 사용법: bash install.sh [--pypi-mirror URL]

# Windows(CRLF) 줄바꿈으로 실행된 경우 자동 재실행
if head -1 "$0" | grep -q $'\r'; then
    tmp=$(mktemp)
    sed 's/\r$//' "$0" > "$tmp"
    exec bash "$tmp" "$@"
fi

set -e
set -o pipefail

INSTALL_DIR="/opt/gpu-monitor"
VENV_DIR="${INSTALL_DIR}/venv"
SERVICE_NAME="gpu-monitor"
PYPI_MIRROR=""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 인자 파싱
while [[ $# -gt 0 ]]; do
    case $1 in
        --pypi-mirror)
            PYPI_MIRROR="$2"
            shift 2
            ;;
        *)
            echo "알 수 없는 인자: $1"
            exit 1
            ;;
    esac
done

echo "========================================="
echo "  GPU Monitor 설치"
echo "========================================="

# 1. 설치 디렉토리 생성
echo "[1/5] 설치 디렉토리 생성: ${INSTALL_DIR}"
sudo mkdir -p "${INSTALL_DIR}"
sudo cp -r "${PROJECT_DIR}/src/"* "${INSTALL_DIR}/"
sudo cp -r "${PROJECT_DIR}/examples" "${INSTALL_DIR}/"

# 2. Python venv 생성
echo "[2/5] Python venv 생성"
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

# 3. 의존성 설치
echo "[3/5] 의존성 설치"
PIP_ARGS=""
if [ -n "${PYPI_MIRROR}" ]; then
    PIP_ARGS="-i ${PYPI_MIRROR} --trusted-host $(echo ${PYPI_MIRROR} | sed 's|https\?://||' | cut -d/ -f1)"
    echo "  PyPI 미러: ${PYPI_MIRROR}"
fi

pip install --upgrade pip ${PIP_ARGS}
pip install ${PIP_ARGS} \
    "httpx>=0.24" \
    "pandas>=1.5" \
    "matplotlib>=3.5" \
    "pyyaml>=6.0" \
    "click>=8.0" \
    "flask>=2.3" \
    "prometheus-client>=0.17"

# editable install
cd "${INSTALL_DIR}"
pip install ${PIP_ARGS} -e .

deactivate

# 4. 설정 파일 복사
echo "[4/5] 설정 파일 복사"
if [ ! -f "${INSTALL_DIR}/config.yaml" ]; then
    sudo cp "${INSTALL_DIR}/examples/config.yaml.example" "${INSTALL_DIR}/config.yaml"
    echo "  config.yaml 생성됨 — VM 목록을 편집하세요: ${INSTALL_DIR}/config.yaml"
fi

# 5. systemd 서비스 등록
echo "[5/5] systemd 서비스 등록"
sudo cp "${SCRIPT_DIR}/gpu-monitor.service" "/etc/systemd/system/${SERVICE_NAME}.service"

# 경로 치환
sudo sed -i "s|__INSTALL_DIR__|${INSTALL_DIR}|g" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo sed -i "s|__VENV_DIR__|${VENV_DIR}|g" "/etc/systemd/system/${SERVICE_NAME}.service"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

echo ""
echo "========================================="
echo "  설치 완료!"
echo "========================================="
echo ""
echo "다음 단계:"
echo "  1. VM 목록 편집: sudo vi ${INSTALL_DIR}/config.yaml"
echo "  2. 서비스 시작:  sudo systemctl start ${SERVICE_NAME}"
echo "  3. 로그 확인:    sudo journalctl -u ${SERVICE_NAME} -f"
echo "  4. 대시보드:     http://<이 서버 IP>:5555"
