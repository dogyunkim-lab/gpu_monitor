#!/bin/bash
# GPU Monitor 설치 스크립트 (RHEL 8 / 폐쇄망)
# 전제: git clone으로 프로젝트를 이미 받은 상태
# 사용법: cd gpu-monitor && bash scripts/install.sh

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="${PROJECT_DIR}/src"
VENV_DIR="${PROJECT_DIR}/venv"
SERVICE_NAME="gpu-monitor"
CONFIG_PATH="${PROJECT_DIR}/config.yaml"

echo "========================================="
echo "  GPU Monitor 설치"
echo "========================================="
echo "  프로젝트 경로: ${PROJECT_DIR}"

# 1. Python venv 생성
echo "[1/4] Python venv 생성: ${VENV_DIR}"
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

# 2. 의존성 설치
echo "[2/4] 의존성 설치"
pip install --upgrade pip
cd "${SRC_DIR}"
pip install -e .

deactivate

# 3. 설정 파일 생성
echo "[3/4] 설정 파일 생성"
if [ ! -f "${CONFIG_PATH}" ]; then
    cp "${PROJECT_DIR}/examples/config.yaml.example" "${CONFIG_PATH}"
    echo "  config.yaml 생성됨 — VM 목록을 편집하세요: ${CONFIG_PATH}"
else
    echo "  config.yaml 이미 존재 — 건너뜀"
fi

# 4. systemd 서비스 등록
echo "[4/4] systemd 서비스 등록"
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=GPU Monitor — DCGM exporter 기반 다중 GPU VM 통합 모니터링
After=network.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
ExecStart=${VENV_DIR}/bin/gpu-monitor -c ${CONFIG_PATH} start
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

echo ""
echo "========================================="
echo "  설치 완료!"
echo "========================================="
echo ""
echo "다음 단계:"
echo "  1. VM 목록 편집: vi ${CONFIG_PATH}"
echo "  2. 서비스 시작:  sudo systemctl start ${SERVICE_NAME}"
echo "  3. 로그 확인:    sudo journalctl -u ${SERVICE_NAME} -f"
echo "  4. 대시보드:     http://<이 서버 IP>:5555"
