"""vLLM 전용 Prometheus scrape config 생성기."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from gpu_monitor.config import AppConfig


def generate_vllm_prometheus_config(config: AppConfig, output_dir: Path | None = None) -> Path:
    """vLLM 타겟 전용 prometheus scrape config YAML 생성.

    각 모델별 target에 model_name 레이블을 relabel로 추가한다.

    Returns:
        생성된 YAML 파일 경로.
    """
    out = Path(output_dir or config.prometheus.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    vc = config.vllm

    # 모델별 static_config — 각 타겟에 model_name 레이블 부여
    static_configs = []
    for m in vc.models:
        entry: dict = {"targets": [m.target], "labels": {"model_name": m.model_name}}
        if m.gpu_vm:
            entry["labels"]["gpu_vm"] = m.gpu_vm
        static_configs.append(entry)

    relabel_configs = [
        {
            "source_labels": ["__address__"],
            "regex": "([^:]+):\\d+",
            "target_label": "instance",
        },
    ]

    scrape_config = {
        "job_name": vc.job_name,
        "scrape_interval": vc.scrape_interval,
        "metrics_path": "/metrics",
        "static_configs": static_configs,
        "relabel_configs": relabel_configs,
    }

    prom_config = {
        "scrape_configs": [scrape_config],
    }

    filepath = out / "vllm_prometheus.yml"
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(prom_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return filepath
