"""prometheus.yml 생성기."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from gpu_monitor.config import AppConfig


def generate_prometheus_config(config: AppConfig, output_dir: Path | None = None) -> Path:
    """prometheus.yml 생성 후 파일 경로 반환."""
    out = Path(output_dir or config.prometheus.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    targets = [f"{vm.host}:{vm.port}" for vm in config.vms]
    labels = {vm.host: vm.name for vm in config.vms if vm.name != vm.host}

    static_configs = [{"targets": targets}]
    if labels:
        static_configs[0]["labels"] = {"cluster": "gpu"}

    # relabel로 VM name → instance 라벨
    relabel_configs = [
        {
            "source_labels": ["__address__"],
            "regex": "([^:]+):\\d+",
            "target_label": "vm",
        },
    ]

    prom_config = {
        "global": {
            "scrape_interval": config.prometheus.scrape_interval,
            "evaluation_interval": config.prometheus.evaluation_interval,
        },
        "rule_files": [
            "rules/*.yml",
        ],
        "scrape_configs": [
            {
                "job_name": config.prometheus.job_name,
                "metrics_path": config.prometheus.metrics_path,
                "scrape_interval": config.prometheus.scrape_interval,
                "static_configs": static_configs,
                "relabel_configs": relabel_configs,
            },
        ],
    }

    filepath = out / "prometheus.yml"
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(prom_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return filepath
