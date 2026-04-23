"""Grafana provisioning + dashboard JSON 생성기."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from gpu_monitor.config import AppConfig


def generate_grafana_provisioning(config: AppConfig, output_dir: Path | None = None) -> dict[str, Path]:
    """Grafana datasource, dashboard provisioning, dashboard JSON 생성.

    Returns:
        dict with keys: datasource, dashboard_provisioning, dashboard_json
    """
    gc = config.grafana
    out = Path(output_dir or gc.output_dir)
    prov = Path(gc.provisioning_dir) if output_dir is None else out / "provisioning"

    paths = {}

    # --- Datasource provisioning ---
    ds_dir = prov / "datasources"
    ds_dir.mkdir(parents=True, exist_ok=True)

    datasource = {
        "apiVersion": 1,
        "datasources": [
            {
                "name": "Prometheus",
                "type": "prometheus",
                "access": "proxy",
                "url": gc.datasource_url,
                "isDefault": True,
                "editable": False,
            },
        ],
    }

    ds_path = ds_dir / "prometheus.yml"
    with open(ds_path, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(datasource, f, default_flow_style=False, sort_keys=False)
    paths["datasource"] = ds_path

    # --- Dashboard provisioning ---
    db_prov_dir = prov / "dashboards"
    db_prov_dir.mkdir(parents=True, exist_ok=True)

    db_provisioning = {
        "apiVersion": 1,
        "providers": [
            {
                "name": "default",
                "orgId": 1,
                "folder": "",
                "type": "file",
                "disableDeletion": False,
                "updateIntervalSeconds": 10,
                "options": {
                    "path": str((out / "dashboards").resolve()),
                    "foldersFromFilesStructure": False,
                },
            },
        ],
    }

    db_prov_path = db_prov_dir / "default.yml"
    with open(db_prov_path, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(db_provisioning, f, default_flow_style=False, sort_keys=False)
    paths["dashboard_provisioning"] = db_prov_path

    # --- Dashboard JSON ---
    dash_dir = out / "dashboards"
    dash_dir.mkdir(parents=True, exist_ok=True)

    dashboard = _build_dashboard(config)
    dash_path = dash_dir / "gpu-cluster.json"
    with open(dash_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dashboard, f, indent=2, ensure_ascii=False)
        f.write("\n")
    paths["dashboard_json"] = dash_path

    return paths


# ---------- Dashboard builder ----------

def _uid() -> str:
    return "gpu-cluster-monitor"


def _ds() -> dict:
    return {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}


def _build_dashboard(config: AppConfig) -> dict:
    title = config.grafana.dashboard_title
    panels = _build_panels()

    return {
        "__inputs": [
            {
                "name": "DS_PROMETHEUS",
                "label": "Prometheus",
                "type": "datasource",
                "pluginId": "prometheus",
            },
        ],
        "uid": _uid(),
        "title": title,
        "tags": ["gpu", "dcgm", "nvidia"],
        "timezone": "browser",
        "editable": True,
        "refresh": "5s",
        "time": {"from": "now-1h", "to": "now"},
        "templating": {
            "list": [
                {
                    "name": "DS_PROMETHEUS",
                    "type": "datasource",
                    "query": "prometheus",
                    "current": {"text": "Prometheus", "value": "Prometheus"},
                },
                {
                    "name": "hostname",
                    "type": "query",
                    "datasource": _ds(),
                    "query": 'label_values(DCGM_FI_DEV_GPU_UTIL, Hostname)',
                    "includeAll": True,
                    "multi": True,
                    "current": {"text": "All", "value": "$__all"},
                },
                {
                    "name": "gpu",
                    "type": "query",
                    "datasource": _ds(),
                    "query": 'label_values(DCGM_FI_DEV_GPU_UTIL{Hostname=~"$hostname"}, gpu)',
                    "includeAll": True,
                    "multi": True,
                    "current": {"text": "All", "value": "$__all"},
                },
            ],
        },
        "panels": panels,
        "schemaVersion": 39,
        "version": 1,
    }


def _panel(id_: int, title: str, type_: str, targets: list, gridPos: dict, **extra) -> dict:
    p = {
        "id": id_,
        "title": title,
        "type": type_,
        "datasource": _ds(),
        "targets": targets,
        "gridPos": gridPos,
    }
    p.update(extra)
    return p


def _target(expr: str, legend: str = "") -> dict:
    t = {"expr": expr, "datasource": _ds(), "refId": "A"}
    if legend:
        t["legendFormat"] = legend
    return t


def _build_panels() -> list:
    panels = []
    pid = 1
    y = 0

    # ===== Row: Overview =====
    panels.append({"id": pid, "type": "row", "title": "Overview", "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "collapsed": False})
    pid += 1; y += 1

    # GPU Count (Stat)
    panels.append(_panel(pid, "GPU Count", "stat",
        [_target('count(DCGM_FI_DEV_GPU_UTIL{Hostname=~"$hostname"})')],
        {"h": 4, "w": 6, "x": 0, "y": y},
        fieldConfig={"defaults": {"unit": "none", "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]}}},
    ))
    pid += 1

    # Average Utilization (Gauge)
    panels.append(_panel(pid, "Avg GPU Utilization", "gauge",
        [_target('avg(DCGM_FI_DEV_GPU_UTIL{Hostname=~"$hostname", gpu=~"$gpu"})')],
        {"h": 4, "w": 6, "x": 6, "y": y},
        fieldConfig={"defaults": {"unit": "percent", "min": 0, "max": 100,
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "green", "value": None}, {"color": "yellow", "value": 70}, {"color": "red", "value": 90}
            ]}}},
    ))
    pid += 1

    # Max Temperature (Gauge)
    panels.append(_panel(pid, "Max Temperature", "gauge",
        [_target('max(DCGM_FI_DEV_GPU_TEMP{Hostname=~"$hostname", gpu=~"$gpu"})')],
        {"h": 4, "w": 6, "x": 12, "y": y},
        fieldConfig={"defaults": {"unit": "celsius", "min": 0, "max": 100,
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "green", "value": None}, {"color": "yellow", "value": 70}, {"color": "red", "value": 83}
            ]}}},
    ))
    pid += 1

    # Total Power (Stat)
    panels.append(_panel(pid, "Total Power", "stat",
        [_target('sum(DCGM_FI_DEV_POWER_USAGE{Hostname=~"$hostname", gpu=~"$gpu"})')],
        {"h": 4, "w": 6, "x": 18, "y": y},
        fieldConfig={"defaults": {"unit": "watt", "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]}}},
    ))
    pid += 1; y += 4

    # ===== Row: Status Table =====
    panels.append({"id": pid, "type": "row", "title": "Status Table", "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "collapsed": False})
    pid += 1; y += 1

    table_targets = [
        {"expr": 'DCGM_FI_DEV_GPU_UTIL{Hostname=~"$hostname", gpu=~"$gpu"}', "datasource": _ds(), "refId": "A", "legendFormat": "", "instant": True, "format": "table"},
        {"expr": 'DCGM_FI_DEV_GPU_TEMP{Hostname=~"$hostname", gpu=~"$gpu"}', "datasource": _ds(), "refId": "B", "legendFormat": "", "instant": True, "format": "table"},
        {"expr": 'DCGM_FI_DEV_POWER_USAGE{Hostname=~"$hostname", gpu=~"$gpu"}', "datasource": _ds(), "refId": "C", "legendFormat": "", "instant": True, "format": "table"},
        {"expr": 'DCGM_FI_DEV_FB_USED{Hostname=~"$hostname", gpu=~"$gpu"}', "datasource": _ds(), "refId": "D", "legendFormat": "", "instant": True, "format": "table"},
        {"expr": 'DCGM_FI_DEV_MEM_COPY_UTIL{Hostname=~"$hostname", gpu=~"$gpu"}', "datasource": _ds(), "refId": "E", "legendFormat": "", "instant": True, "format": "table"},
    ]
    panels.append(_panel(pid, "GPU Status Table", "table", table_targets,
        {"h": 8, "w": 24, "x": 0, "y": y},
        transformations=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "UUID": True, "device": True, "job": True, "instance": True},
                "renameByName": {
                    "Hostname": "Host", "gpu": "GPU",
                    "Value #A": "Util%", "Value #B": "Temp°C", "Value #C": "Power W",
                    "Value #D": "VRAM MiB", "Value #E": "MemBW%",
                },
            }},
        ],
    ))
    pid += 1; y += 8

    # ===== Row: Utilization Time Series =====
    panels.append({"id": pid, "type": "row", "title": "Utilization", "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "collapsed": False})
    pid += 1; y += 1

    # Tensor Core + DRAM Active + GPU Util + Mem Copy Util
    panels.append(_panel(pid, "Tensor Core Active", "timeseries",
        [_target('DCGM_FI_PROF_PIPE_TENSOR_ACTIVE{Hostname=~"$hostname", gpu=~"$gpu"}', '{{Hostname}} GPU{{gpu}}')],
        {"h": 8, "w": 12, "x": 0, "y": y},
        fieldConfig={"defaults": {"unit": "percentunit", "min": 0, "max": 1, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1

    panels.append(_panel(pid, "DRAM Active", "timeseries",
        [_target('DCGM_FI_PROF_DRAM_ACTIVE{Hostname=~"$hostname", gpu=~"$gpu"}', '{{Hostname}} GPU{{gpu}}')],
        {"h": 8, "w": 12, "x": 12, "y": y},
        fieldConfig={"defaults": {"unit": "percentunit", "min": 0, "max": 1, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1; y += 8

    panels.append(_panel(pid, "GPU Utilization", "timeseries",
        [_target('DCGM_FI_DEV_GPU_UTIL{Hostname=~"$hostname", gpu=~"$gpu"}', '{{Hostname}} GPU{{gpu}}')],
        {"h": 8, "w": 12, "x": 0, "y": y},
        fieldConfig={"defaults": {"unit": "percent", "min": 0, "max": 100, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1

    panels.append(_panel(pid, "Memory Copy Utilization", "timeseries",
        [_target('DCGM_FI_DEV_MEM_COPY_UTIL{Hostname=~"$hostname", gpu=~"$gpu"}', '{{Hostname}} GPU{{gpu}}')],
        {"h": 8, "w": 12, "x": 12, "y": y},
        fieldConfig={"defaults": {"unit": "percent", "min": 0, "max": 100, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1; y += 8

    # ===== Row: Temperature & Power =====
    panels.append({"id": pid, "type": "row", "title": "Temperature & Power", "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "collapsed": False})
    pid += 1; y += 1

    panels.append(_panel(pid, "Temperature", "timeseries",
        [_target('DCGM_FI_DEV_GPU_TEMP{Hostname=~"$hostname", gpu=~"$gpu"}', '{{Hostname}} GPU{{gpu}}')],
        {"h": 8, "w": 12, "x": 0, "y": y},
        fieldConfig={"defaults": {"unit": "celsius", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10},
            "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "red", "value": 83}]}}},
    ))
    pid += 1

    panels.append(_panel(pid, "Power Usage", "timeseries",
        [_target('DCGM_FI_DEV_POWER_USAGE{Hostname=~"$hostname", gpu=~"$gpu"}', '{{Hostname}} GPU{{gpu}}')],
        {"h": 8, "w": 12, "x": 12, "y": y},
        fieldConfig={"defaults": {"unit": "watt", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1; y += 8

    # ===== Row: VRAM =====
    panels.append({"id": pid, "type": "row", "title": "VRAM", "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "collapsed": False})
    pid += 1; y += 1

    panels.append(_panel(pid, "VRAM Usage (MiB)", "timeseries",
        [_target('DCGM_FI_DEV_FB_USED{Hostname=~"$hostname", gpu=~"$gpu"}', '{{Hostname}} GPU{{gpu}}')],
        {"h": 8, "w": 12, "x": 0, "y": y},
        fieldConfig={"defaults": {"unit": "decmbytes", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1

    panels.append(_panel(pid, "VRAM Utilization (%)", "timeseries",
        [_target('DCGM_FI_DEV_FB_USED{Hostname=~"$hostname", gpu=~"$gpu"} / (DCGM_FI_DEV_FB_USED{Hostname=~"$hostname", gpu=~"$gpu"} + DCGM_FI_DEV_FB_FREE{Hostname=~"$hostname", gpu=~"$gpu"}) * 100', '{{Hostname}} GPU{{gpu}}')],
        {"h": 8, "w": 12, "x": 12, "y": y},
        fieldConfig={"defaults": {"unit": "percent", "min": 0, "max": 100, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1; y += 8

    # ===== Row: Interconnect =====
    panels.append({"id": pid, "type": "row", "title": "Interconnect", "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "collapsed": False})
    pid += 1; y += 1

    panels.append(_panel(pid, "NVLink Bandwidth", "timeseries",
        [
            _target('DCGM_FI_DEV_NVLINK_BANDWIDTH_TX_TOTAL{Hostname=~"$hostname", gpu=~"$gpu"}', '{{Hostname}} GPU{{gpu}} TX'),
            _target('DCGM_FI_DEV_NVLINK_BANDWIDTH_RX_TOTAL{Hostname=~"$hostname", gpu=~"$gpu"}', '{{Hostname}} GPU{{gpu}} RX'),
        ],
        {"h": 8, "w": 8, "x": 0, "y": y},
        fieldConfig={"defaults": {"unit": "Bps", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    # Fix refIds for multi-target
    panels[-1]["targets"][1]["refId"] = "B"
    pid += 1

    panels.append(_panel(pid, "PCIe TX Bandwidth", "timeseries",
        [_target('DCGM_FI_DEV_PCIE_TX_THROUGHPUT{Hostname=~"$hostname", gpu=~"$gpu"}', '{{Hostname}} GPU{{gpu}}')],
        {"h": 8, "w": 8, "x": 8, "y": y},
        fieldConfig={"defaults": {"unit": "Bps", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1

    panels.append(_panel(pid, "PCIe RX Bandwidth", "timeseries",
        [_target('DCGM_FI_DEV_PCIE_RX_THROUGHPUT{Hostname=~"$hostname", gpu=~"$gpu"}', '{{Hostname}} GPU{{gpu}}')],
        {"h": 8, "w": 8, "x": 16, "y": y},
        fieldConfig={"defaults": {"unit": "Bps", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))

    return panels
