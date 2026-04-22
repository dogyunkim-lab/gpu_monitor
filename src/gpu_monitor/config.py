"""YAML 설정 로드 모듈."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


@dataclass
class VMConfig:
    host: str
    port: int = 9400
    name: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = self.host

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/metrics"


@dataclass
class CollectorConfig:
    interval_seconds: float = 1.0
    timeout_seconds: float = 2.0
    max_consecutive_failures: int = 3


@dataclass
class StorageConfig:
    db_path: str = "gpu_metrics.db"
    retention_days: int = 7


@dataclass
class RecorderConfig:
    interval_ms: int = 100
    output_dir: str = "recordings"


@dataclass
class AlertConfig:
    gpu_util_threshold: float = 95.0
    gpu_util_duration_seconds: int = 10
    temperature_threshold: float = 80.0
    vram_util_threshold: float = 95.0
    log_file: str = "alerts.log"


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 5555
    refresh_seconds: int = 5


@dataclass
class AppConfig:
    vms: List[VMConfig] = field(default_factory=list)
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    recorder: RecorderConfig = field(default_factory=RecorderConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    web: WebConfig = field(default_factory=WebConfig)


def load_config(path: str | Path | None = None) -> AppConfig:
    """YAML 설정 파일 로드. 없으면 기본값 반환."""
    if path is None:
        path = os.environ.get("GPU_MONITOR_CONFIG", "config.yaml")
    path = Path(path)

    if not path.exists():
        return AppConfig()

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    vms = [VMConfig(**vm) for vm in raw.get("vms", [])]

    collector = CollectorConfig(**raw.get("collector", {}))
    storage = StorageConfig(**raw.get("storage", {}))
    recorder = RecorderConfig(**raw.get("recorder", {}))
    alerts = AlertConfig(**raw.get("alerts", {}))
    web = WebConfig(**raw.get("web", {}))

    return AppConfig(
        vms=vms,
        collector=collector,
        storage=storage,
        recorder=recorder,
        alerts=alerts,
        web=web,
    )
