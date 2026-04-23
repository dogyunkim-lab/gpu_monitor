"""공통 테스트 fixture."""

import os
import sys

import pytest

# src/ 를 import path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gpu_monitor.config import AppConfig, VMConfig, AlertConfig, PrometheusConfig, GrafanaConfig, VLLMConfig, VLLMModelConfig


@pytest.fixture
def sample_config(tmp_path):
    return AppConfig(
        vms=[
            VMConfig(host="gpu-vm-01", port=9400, name="GPU-VM-01"),
            VMConfig(host="gpu-vm-02", port=9400, name="GPU-VM-02"),
        ],
        alerts=AlertConfig(
            gpu_util_threshold=90.0,
            gpu_util_duration="1m",
            temperature_threshold=80.0,
            vram_util_threshold=90.0,
            power_threshold=300.0,
        ),
        prometheus=PrometheusConfig(
            output_dir=str(tmp_path / "prometheus"),
            scrape_interval="5s",
            evaluation_interval="15s",
        ),
        grafana=GrafanaConfig(
            output_dir=str(tmp_path / "grafana"),
            provisioning_dir=str(tmp_path / "grafana" / "provisioning"),
            datasource_url="http://localhost:9090",
        ),
    )
