"""vLLM Grafana dashboard JSON 생성기."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gpu_monitor.config import AppConfig


def generate_vllm_grafana_dashboard(config: AppConfig, output_dir: Path | None = None) -> dict[str, Path]:
    """vLLM 대시보드 JSON 생성.

    Returns:
        dict with key: dashboard_json → Path
    """
    out = Path(output_dir or config.grafana.output_dir)
    dash_dir = out / "dashboards"
    dash_dir.mkdir(parents=True, exist_ok=True)

    dashboard = _build_dashboard()
    dash_path = dash_dir / "vllm-monitor.json"
    with open(dash_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dashboard, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return {"dashboard_json": dash_path}


# ---------- helpers ----------

def _ds() -> dict:
    return {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}


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


def _target(expr: str, legend: str = "", ref: str = "A") -> dict:
    t = {"expr": expr, "datasource": _ds(), "refId": ref}
    if legend:
        t["legendFormat"] = legend
    return t


def _row(id_: int, title: str, y: int) -> dict:
    return {"id": id_, "type": "row", "title": title, "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "collapsed": False}


_MODEL_FILTER = '{model_name=~"$model", instance=~"$instance"}'


# ---------- dashboard ----------

def _build_dashboard() -> dict:
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
        "uid": "vllm-monitor",
        "title": "vLLM Inference Monitor",
        "tags": ["vllm", "llm", "inference"],
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
                    "name": "model",
                    "label": "Model",
                    "type": "query",
                    "datasource": _ds(),
                    "query": "label_values(vllm:num_requests_running, model_name)",
                    "includeAll": True,
                    "multi": True,
                    "current": {"text": "All", "value": "$__all"},
                },
                {
                    "name": "instance",
                    "label": "Instance",
                    "type": "query",
                    "datasource": _ds(),
                    "query": "label_values(vllm:num_requests_running, instance)",
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


def _build_panels() -> list:
    panels = []
    pid = 1
    y = 0
    f = _MODEL_FILTER

    # ===== Row 1: Overview =====
    panels.append(_row(pid, "Overview", y))
    pid += 1; y += 1

    # Running Requests (stat)
    panels.append(_panel(pid, "Running Requests", "stat",
        [_target(f'vllm:num_requests_running{f}')],
        {"h": 4, "w": 5, "x": 0, "y": y},
        fieldConfig={"defaults": {"unit": "none", "thresholds": {"mode": "absolute", "steps": [
            {"color": "green", "value": None}, {"color": "yellow", "value": 10}, {"color": "red", "value": 50},
        ]}}},
    ))
    pid += 1

    # Waiting Requests (stat)
    panels.append(_panel(pid, "Waiting Requests", "stat",
        [_target(f'vllm:num_requests_waiting{f}')],
        {"h": 4, "w": 5, "x": 5, "y": y},
        fieldConfig={"defaults": {"unit": "none", "thresholds": {"mode": "absolute", "steps": [
            {"color": "green", "value": None}, {"color": "orange", "value": 5}, {"color": "red", "value": 20},
        ]}}},
    ))
    pid += 1

    # Swapped Requests (stat)
    panels.append(_panel(pid, "Swapped Requests", "stat",
        [_target(f'vllm:num_requests_swapped{f}')],
        {"h": 4, "w": 5, "x": 10, "y": y},
        fieldConfig={"defaults": {"unit": "none", "thresholds": {"mode": "absolute", "steps": [
            {"color": "green", "value": None}, {"color": "red", "value": 1},
        ]}}},
    ))
    pid += 1

    # Total Prompt Tokens/s (stat)
    panels.append(_panel(pid, "Prompt Tokens/s", "stat",
        [_target(f'sum(rate(vllm:prompt_tokens_total{f}[1m]))')],
        {"h": 4, "w": 4, "x": 15, "y": y},
        fieldConfig={"defaults": {"unit": "none", "decimals": 1, "thresholds": {"mode": "absolute", "steps": [
            {"color": "blue", "value": None},
        ]}}},
    ))
    pid += 1

    # Total Gen Tokens/s (stat)
    panels.append(_panel(pid, "Gen Tokens/s", "stat",
        [_target(f'sum(rate(vllm:generation_tokens_total{f}[1m]))')],
        {"h": 4, "w": 5, "x": 19, "y": y},
        fieldConfig={"defaults": {"unit": "none", "decimals": 1, "thresholds": {"mode": "absolute", "steps": [
            {"color": "blue", "value": None},
        ]}}},
    ))
    pid += 1; y += 4

    # ===== Row 2: Latency =====
    panels.append(_row(pid, "Latency", y))
    pid += 1; y += 1

    # TTFT (p50/p90/p99)
    panels.append(_panel(pid, "Time to First Token (TTFT)", "timeseries",
        [
            _target(f'histogram_quantile(0.5, sum(rate(vllm:time_to_first_token_seconds_bucket{f}[1m])) by (le, model_name))', "p50 {{{{model_name}}}}", "A"),
            _target(f'histogram_quantile(0.9, sum(rate(vllm:time_to_first_token_seconds_bucket{f}[1m])) by (le, model_name))', "p90 {{{{model_name}}}}", "B"),
            _target(f'histogram_quantile(0.99, sum(rate(vllm:time_to_first_token_seconds_bucket{f}[1m])) by (le, model_name))', "p99 {{{{model_name}}}}", "C"),
        ],
        {"h": 8, "w": 8, "x": 0, "y": y},
        fieldConfig={"defaults": {"unit": "s", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1

    # E2E Request Latency (p50/p90/p99)
    panels.append(_panel(pid, "E2E Request Latency", "timeseries",
        [
            _target(f'histogram_quantile(0.5, sum(rate(vllm:e2e_request_latency_seconds_bucket{f}[1m])) by (le, model_name))', "p50 {{{{model_name}}}}", "A"),
            _target(f'histogram_quantile(0.9, sum(rate(vllm:e2e_request_latency_seconds_bucket{f}[1m])) by (le, model_name))', "p90 {{{{model_name}}}}", "B"),
            _target(f'histogram_quantile(0.99, sum(rate(vllm:e2e_request_latency_seconds_bucket{f}[1m])) by (le, model_name))', "p99 {{{{model_name}}}}", "C"),
        ],
        {"h": 8, "w": 8, "x": 8, "y": y},
        fieldConfig={"defaults": {"unit": "s", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1

    # Time per Output Token (p50/p90/p99)
    panels.append(_panel(pid, "Time per Output Token", "timeseries",
        [
            _target(f'histogram_quantile(0.5, sum(rate(vllm:time_per_output_token_seconds_bucket{f}[1m])) by (le, model_name))', "p50 {{{{model_name}}}}", "A"),
            _target(f'histogram_quantile(0.9, sum(rate(vllm:time_per_output_token_seconds_bucket{f}[1m])) by (le, model_name))', "p90 {{{{model_name}}}}", "B"),
            _target(f'histogram_quantile(0.99, sum(rate(vllm:time_per_output_token_seconds_bucket{f}[1m])) by (le, model_name))', "p99 {{{{model_name}}}}", "C"),
        ],
        {"h": 8, "w": 8, "x": 16, "y": y},
        fieldConfig={"defaults": {"unit": "s", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1; y += 8

    # ===== Row 3: Queue & Processing =====
    panels.append(_row(pid, "Queue & Processing", y))
    pid += 1; y += 1

    # Queue Wait Time
    panels.append(_panel(pid, "Avg Queue Wait Time", "timeseries",
        [_target(f'rate(vllm:request_queue_time_seconds_sum{f}[1m]) / rate(vllm:request_queue_time_seconds_count{f}[1m])', "{{{{model_name}}}}")],
        {"h": 8, "w": 6, "x": 0, "y": y},
        fieldConfig={"defaults": {"unit": "s", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1

    # Prefill Time
    panels.append(_panel(pid, "Avg Prefill Time", "timeseries",
        [_target(f'rate(vllm:request_prefill_time_seconds_sum{f}[1m]) / rate(vllm:request_prefill_time_seconds_count{f}[1m])', "{{{{model_name}}}}")],
        {"h": 8, "w": 6, "x": 6, "y": y},
        fieldConfig={"defaults": {"unit": "s", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1

    # Decode Time
    panels.append(_panel(pid, "Avg Decode Time", "timeseries",
        [_target(f'rate(vllm:request_decode_time_seconds_sum{f}[1m]) / rate(vllm:request_decode_time_seconds_count{f}[1m])', "{{{{model_name}}}}")],
        {"h": 8, "w": 6, "x": 12, "y": y},
        fieldConfig={"defaults": {"unit": "s", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1

    # Request Queue Depth (running + waiting)
    panels.append(_panel(pid, "Request Queue Depth", "timeseries",
        [
            _target(f'vllm:num_requests_running{f}', "running {{{{model_name}}}}", "A"),
            _target(f'vllm:num_requests_waiting{f}', "waiting {{{{model_name}}}}", "B"),
        ],
        {"h": 8, "w": 6, "x": 18, "y": y},
        fieldConfig={"defaults": {"unit": "none", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10, "stacking": {"mode": "normal"}}}},
    ))
    pid += 1; y += 8

    # ===== Row 4: Token Distribution =====
    panels.append(_row(pid, "Token Distribution", y))
    pid += 1; y += 1

    # Prompt Tokens/Request (p50/p90)
    panels.append(_panel(pid, "Prompt Tokens/Request", "timeseries",
        [
            _target(f'histogram_quantile(0.5, sum(rate(vllm:request_prompt_tokens_bucket{f}[1m])) by (le, model_name))', "p50 {{{{model_name}}}}", "A"),
            _target(f'histogram_quantile(0.9, sum(rate(vllm:request_prompt_tokens_bucket{f}[1m])) by (le, model_name))', "p90 {{{{model_name}}}}", "B"),
        ],
        {"h": 8, "w": 8, "x": 0, "y": y},
        fieldConfig={"defaults": {"unit": "none", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1

    # Gen Tokens/Request (p50/p90)
    panels.append(_panel(pid, "Gen Tokens/Request", "timeseries",
        [
            _target(f'histogram_quantile(0.5, sum(rate(vllm:request_generation_tokens_bucket{f}[1m])) by (le, model_name))', "p50 {{{{model_name}}}}", "A"),
            _target(f'histogram_quantile(0.9, sum(rate(vllm:request_generation_tokens_bucket{f}[1m])) by (le, model_name))', "p90 {{{{model_name}}}}", "B"),
        ],
        {"h": 8, "w": 8, "x": 8, "y": y},
        fieldConfig={"defaults": {"unit": "none", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))
    pid += 1

    # Throughput (tokens/s) — prompt + gen
    panels.append(_panel(pid, "Throughput (tokens/s)", "timeseries",
        [
            _target(f'rate(vllm:prompt_tokens_total{f}[1m])', "prompt {{{{model_name}}}}", "A"),
            _target(f'rate(vllm:generation_tokens_total{f}[1m])', "gen {{{{model_name}}}}", "B"),
        ],
        {"h": 8, "w": 8, "x": 16, "y": y},
        fieldConfig={"defaults": {"unit": "none", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10, "stacking": {"mode": "normal"}}}},
    ))
    pid += 1; y += 8

    # ===== Row 5: Cache & Success =====
    panels.append(_row(pid, "Cache & Success", y))
    pid += 1; y += 1

    # GPU KV Cache Usage
    panels.append(_panel(pid, "GPU KV Cache Usage", "gauge",
        [_target(f'vllm:gpu_cache_usage_perc{f}', "{{{{model_name}}}}")],
        {"h": 6, "w": 8, "x": 0, "y": y},
        fieldConfig={"defaults": {"unit": "percentunit", "min": 0, "max": 1,
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "green", "value": None}, {"color": "yellow", "value": 0.7}, {"color": "red", "value": 0.9},
            ]}}},
    ))
    pid += 1

    # CPU KV Cache Usage
    panels.append(_panel(pid, "CPU KV Cache Usage", "gauge",
        [_target(f'vllm:cpu_cache_usage_perc{f}', "{{{{model_name}}}}")],
        {"h": 6, "w": 8, "x": 8, "y": y},
        fieldConfig={"defaults": {"unit": "percentunit", "min": 0, "max": 1,
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "green", "value": None}, {"color": "yellow", "value": 0.5}, {"color": "red", "value": 0.8},
            ]}}},
    ))
    pid += 1

    # Request Success Rate by finish_reason
    panels.append(_panel(pid, "Request Success Rate", "timeseries",
        [_target(f'rate(vllm:request_success_total{f}[1m])', "{{{{model_name}}}} {{{{finish_reason}}}}")],
        {"h": 6, "w": 8, "x": 16, "y": y},
        fieldConfig={"defaults": {"unit": "reqps", "min": 0, "custom": {"drawStyle": "line", "fillOpacity": 10}}},
    ))

    return panels
