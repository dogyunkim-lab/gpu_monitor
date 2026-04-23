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
class AlertConfig:
    gpu_util_threshold: float = 95.0
    gpu_util_duration: str = "1m"
    temperature_threshold: float = 83.0
    vram_util_threshold: float = 95.0
    power_threshold: float = 350.0


@dataclass
class PrometheusConfig:
    output_dir: str = "/etc/prometheus"
    scrape_interval: str = "5s"
    evaluation_interval: str = "15s"
    job_name: str = "dcgm"
    metrics_path: str = "/metrics"


@dataclass
class GrafanaConfig:
    output_dir: str = "/etc/grafana"
    provisioning_dir: str = "/etc/grafana/provisioning"
    datasource_url: str = "http://localhost:9090"
    dashboard_title: str = "GPU Cluster Monitor"


@dataclass
class VLLMModelConfig:
    host: str
    port: int = 8000
    model_name: str = ""
    gpu_vm: str = ""

    @property
    def metrics_url(self) -> str:
        return f"http://{self.host}:{self.port}/metrics"

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass
class VLLMConfig:
    models: List[VLLMModelConfig] = field(default_factory=list)
    scrape_interval: str = "1s"
    job_name: str = "vllm"


@dataclass
class AppConfig:
    vms: List[VMConfig] = field(default_factory=list)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    prometheus: PrometheusConfig = field(default_factory=PrometheusConfig)
    grafana: GrafanaConfig = field(default_factory=GrafanaConfig)
    vllm: VLLMConfig = field(default_factory=VLLMConfig)


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
    alerts = AlertConfig(**raw.get("alerts", {}))
    prometheus = PrometheusConfig(**raw.get("prometheus", {}))
    grafana = GrafanaConfig(**raw.get("grafana", {}))

    vllm_raw = raw.get("vllm", {})
    vllm_models = [VLLMModelConfig(**m) for m in vllm_raw.pop("models", [])]
    vllm = VLLMConfig(models=vllm_models, **vllm_raw)

    return AppConfig(
        vms=vms,
        alerts=alerts,
        prometheus=prometheus,
        grafana=grafana,
        vllm=vllm,
    )
