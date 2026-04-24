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

    # vLLM 모델이 설정되어 있으면 vllm scrape config를 prometheus.yml에 직접 포함
    if config.vllm.models:
        vc = config.vllm
        vllm_static_configs = []
        for m in vc.models:
            entry: dict = {"targets": [m.target], "labels": {"model_name": m.model_name}}
            if m.gpu_vm:
                entry["labels"]["gpu_vm"] = m.gpu_vm
            vllm_static_configs.append(entry)

        prom_config["scrape_configs"].append({
            "job_name": vc.job_name,
            "scrape_interval": vc.scrape_interval,
            "metrics_path": "/metrics",
            "static_configs": vllm_static_configs,
            "relabel_configs": [
                {
                    "source_labels": ["__address__"],
                    "regex": "([^:]+):\\d+",
                    "target_label": "instance",
                },
            ],
        })

    # node_exporter가 활성화되어 있으면 node scrape job 추가 (vms 호스트 재사용)
    nc = config.node_exporter
    if nc.enabled and config.vms:
        node_targets = [f"{vm.host}:{nc.port}" for vm in config.vms]
        prom_config["scrape_configs"].append({
            "job_name": nc.job_name,
            "scrape_interval": nc.scrape_interval,
            "metrics_path": "/metrics",
            "static_configs": [{"targets": node_targets}],
            "relabel_configs": [
                {
                    "source_labels": ["__address__"],
                    "regex": "([^:]+):\\d+",
                    "target_label": "vm",
                },
            ],
        })

    filepath = out / "prometheus.yml"
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(prom_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return filepath
