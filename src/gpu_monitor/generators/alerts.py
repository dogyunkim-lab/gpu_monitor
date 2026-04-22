"""Prometheus alerting rules YAML 생성기."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from gpu_monitor.config import AppConfig


def generate_alert_rules(config: AppConfig, output_dir: Path | None = None) -> Path:
    """Prometheus alert rules YAML 생성 후 파일 경로 반환."""
    out = Path(output_dir or config.prometheus.output_dir) / "rules"
    out.mkdir(parents=True, exist_ok=True)

    ac = config.alerts

    rules = {
        "groups": [
            {
                "name": "gpu_alerts",
                "rules": [
                    {
                        "alert": "HighGPUUtilization",
                        "expr": f"DCGM_FI_DEV_GPU_UTIL > {ac.gpu_util_threshold}",
                        "for": ac.gpu_util_duration,
                        "labels": {"severity": "warning"},
                        "annotations": {
                            "summary": "GPU {{ $labels.gpu }} on {{ $labels.Hostname }} utilization > {{ $value }}%",
                            "description": f"GPU 사용률이 {ac.gpu_util_threshold}%를 {ac.gpu_util_duration} 이상 초과했습니다.",
                        },
                    },
                    {
                        "alert": "HighGPUTemperature",
                        "expr": f"DCGM_FI_DEV_GPU_TEMP > {ac.temperature_threshold}",
                        "for": "30s",
                        "labels": {"severity": "critical"},
                        "annotations": {
                            "summary": "GPU {{ $labels.gpu }} on {{ $labels.Hostname }} temperature {{ $value }}°C",
                            "description": f"GPU 온도가 {ac.temperature_threshold}°C를 초과했습니다.",
                        },
                    },
                    {
                        "alert": "HighVRAMUtilization",
                        "expr": (
                            "DCGM_FI_DEV_FB_USED / "
                            "(DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE) * 100 "
                            f"> {ac.vram_util_threshold}"
                        ),
                        "for": "1m",
                        "labels": {"severity": "warning"},
                        "annotations": {
                            "summary": "GPU {{ $labels.gpu }} on {{ $labels.Hostname }} VRAM > {{ $value }}%",
                            "description": f"VRAM 사용률이 {ac.vram_util_threshold}%를 초과했습니다.",
                        },
                    },
                    {
                        "alert": "HighPowerUsage",
                        "expr": f"DCGM_FI_DEV_POWER_USAGE > {ac.power_threshold}",
                        "for": "1m",
                        "labels": {"severity": "warning"},
                        "annotations": {
                            "summary": "GPU {{ $labels.gpu }} on {{ $labels.Hostname }} power {{ $value }}W",
                            "description": f"GPU 전력 소비가 {ac.power_threshold}W를 초과했습니다.",
                        },
                    },
                    {
                        "alert": "DCGMExporterDown",
                        "expr": "up{job=\"dcgm\"} == 0",
                        "for": "1m",
                        "labels": {"severity": "critical"},
                        "annotations": {
                            "summary": "DCGM exporter down on {{ $labels.instance }}",
                            "description": "DCGM exporter가 1분 이상 응답하지 않습니다.",
                        },
                    },
                ],
            },
        ],
    }

    filepath = out / "gpu_alerts.yml"
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(rules, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return filepath
