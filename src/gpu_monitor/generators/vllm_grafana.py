"""vLLM Grafana dashboard JSON 생성기 — 진단 대시보드.

대시보드 구성 (6개 섹션):
  1. 현재 상태 — 핵심 수치 4개를 한눈에 파악
  2. E2E 시간 분해 — phantom time 시각화 (핵심 진단)
  3. 요청 특성 — 프롬프트/이터레이션 토큰 분포
  4. 동시성 & 자원 — Running/Waiting/Swapped, KV Cache, Preemption
  5. 처리량 & 병목 분리 — Token 처리량, Inference vs E2E
  6. 분포 분석 — TTFT 히트맵, 요청 성공률
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gpu_monitor.config import AppConfig


def generate_vllm_grafana_dashboard(config: AppConfig, output_dir: Path | None = None) -> dict[str, Path]:
    """vLLM 진단 대시보드 JSON 생성.

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


# ────────────────────────────────────────────────────────────────
# constants & helpers
# ────────────────────────────────────────────────────────────────

_F = '{model_name=~"$model", instance=~"$instance"}'
_IV = "$interval"


def _ds() -> dict:
    return {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}


def _target(expr: str, legend: str = "", ref: str = "A", fmt: str = "") -> dict:
    t: dict = {"expr": expr, "datasource": _ds(), "refId": ref}
    if legend:
        t["legendFormat"] = legend
    if fmt:
        t["format"] = fmt
    return t


def _row(id_: int, title: str, y: int) -> dict:
    return {
        "id": id_, "type": "row", "title": title,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
        "collapsed": False,
    }


def _stat_panel(
    id_: int, title: str, desc: str,
    expr: str, gridPos: dict,
    unit: str = "none", thresholds: list | None = None,
) -> dict:
    steps = thresholds or [{"color": "green", "value": None}]
    return {
        "id": id_, "title": title, "description": desc,
        "type": "stat", "datasource": _ds(),
        "targets": [_target(expr)],
        "gridPos": gridPos,
        "fieldConfig": {"defaults": {
            "unit": unit,
            "thresholds": {"mode": "absolute", "steps": steps},
        }},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}},
    }


def _gauge_panel(
    id_: int, title: str, desc: str,
    expr: str, gridPos: dict,
    unit: str = "percentunit", thresholds: list | None = None,
) -> dict:
    steps = thresholds or [{"color": "green", "value": None}]
    return {
        "id": id_, "title": title, "description": desc,
        "type": "gauge", "datasource": _ds(),
        "targets": [_target(expr)],
        "gridPos": gridPos,
        "fieldConfig": {"defaults": {
            "unit": unit, "min": 0, "max": 1,
            "thresholds": {"mode": "absolute", "steps": steps},
        }},
    }


def _ts_panel(
    id_: int, title: str, desc: str,
    targets: list, gridPos: dict,
    unit: str = "s", ymin: float = 0, ymax: float | None = None,
    fill: int = 10, stacking: bool = False,
    thresholds: list | None = None, overrides: list | None = None,
) -> dict:
    custom: dict = {
        "drawStyle": "line", "lineWidth": 2,
        "fillOpacity": fill, "pointSize": 5, "showPoints": "never",
    }
    if stacking:
        custom["stacking"] = {"mode": "normal"}
    if thresholds:
        custom["thresholdsStyle"] = {"mode": "line"}

    defaults: dict = {"unit": unit, "min": ymin, "custom": custom}
    if ymax is not None:
        defaults["max"] = ymax
    if thresholds:
        defaults["thresholds"] = {"mode": "absolute", "steps": thresholds}

    fc: dict = {"defaults": defaults}
    if overrides:
        fc["overrides"] = overrides

    return {
        "id": id_, "title": title, "description": desc,
        "type": "timeseries", "datasource": _ds(),
        "targets": targets, "gridPos": gridPos,
        "fieldConfig": fc,
        "options": {
            "legend": {"displayMode": "table", "placement": "bottom",
                       "calcs": ["lastNotNull", "mean"]},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
    }


# ────────────────────────────────────────────────────────────────
# dashboard
# ────────────────────────────────────────────────────────────────

def _build_dashboard() -> dict:
    return {
        "__inputs": [{
            "name": "DS_PROMETHEUS",
            "label": "Prometheus",
            "type": "datasource",
            "pluginId": "prometheus",
        }],
        "uid": "vllm-monitor",
        "title": "vLLM 서비스 모니터링 & 진단",
        "tags": ["vllm", "llm", "inference", "diagnostic"],
        "timezone": "browser",
        "editable": True,
        "refresh": "5s",
        "time": {"from": "now-30m", "to": "now"},
        "templating": {"list": [
            {
                "name": "DS_PROMETHEUS",
                "type": "datasource",
                "query": "prometheus",
                "current": {"text": "Prometheus", "value": "Prometheus"},
            },
            {
                "name": "model", "label": "모델",
                "type": "query", "datasource": _ds(),
                "query": "label_values(vllm:num_requests_running, model_name)",
                "includeAll": True, "multi": True,
                "current": {"text": "All", "value": "$__all"},
            },
            {
                "name": "instance", "label": "서버",
                "type": "query", "datasource": _ds(),
                "query": "label_values(vllm:num_requests_running, instance)",
                "includeAll": True, "multi": True,
                "current": {"text": "All", "value": "$__all"},
            },
            {
                "name": "interval", "label": "집계 간격",
                "type": "interval",
                "query": "1m,5m,10m,30m,1h",
                "current": {"text": "1m", "value": "1m"},
                "auto": True, "auto_count": 30, "auto_min": "10s",
            },
        ]},
        "panels": _build_panels(),
        "schemaVersion": 39,
        "version": 3,
    }


# ────────────────────────────────────────────────────────────────
# panels
# ────────────────────────────────────────────────────────────────

def _build_panels() -> list:  # noqa: C901 — 패널 구성 함수라 길이 허용
    panels: list = []
    pid = 1
    y = 0
    f = _F
    iv = _IV

    # ================================================================
    # Section 1: 현재 상태
    # ================================================================
    panels.append(_row(pid, "현재 상태", y)); pid += 1; y += 1

    panels.append(_stat_panel(pid, "처리 중 요청",
        "현재 GPU에서 추론이 진행 중인 요청 수.\n"
        "이 값이 높으면 서버가 활발히 일하고 있는 상태.",
        f"sum(vllm:num_requests_running{f})",
        {"h": 4, "w": 6, "x": 0, "y": y},
        thresholds=[
            {"color": "green", "value": None},
            {"color": "orange", "value": 50},
            {"color": "red", "value": 100},
        ],
    )); pid += 1

    panels.append(_stat_panel(pid, "대기 중 요청",
        "GPU 자원(KV Cache) 부족으로 큐에서 대기 중인 요청 수.\n"
        "0이 정상. 지속적으로 높으면 서버 증설 필요.",
        f"sum(vllm:num_requests_waiting{f})",
        {"h": 4, "w": 6, "x": 6, "y": y},
        thresholds=[
            {"color": "green", "value": None},
            {"color": "orange", "value": 5},
            {"color": "red", "value": 20},
        ],
    )); pid += 1

    panels.append(_stat_panel(pid, "첫 토큰 응답시간 (p90)",
        "요청 후 첫 토큰 생성까지 걸리는 시간.\n"
        "사용자 체감 '대기 시간'에 해당.\n"
        "p90 = 전체 요청의 90%가 이 시간 이내.",
        f"histogram_quantile(0.9, sum(rate(vllm:time_to_first_token_seconds_bucket{f}[{iv}])) by (le))",
        {"h": 4, "w": 6, "x": 12, "y": y},
        unit="s",
        thresholds=[
            {"color": "green", "value": None},
            {"color": "orange", "value": 1},
            {"color": "red", "value": 3},
        ],
    )); pid += 1

    panels.append(_gauge_panel(pid, "KV Cache 사용률",
        "GPU 메모리에서 KV Cache가 차지하는 비율.\n"
        "90% 이상이면 새 요청을 받을 수 없어 큐에 쌓이기 시작.\n"
        "Preemption 없이도 처리량이 크게 저하됨.",
        f"avg(vllm:gpu_cache_usage_perc{f})",
        {"h": 4, "w": 6, "x": 18, "y": y},
        thresholds=[
            {"color": "green", "value": None},
            {"color": "orange", "value": 0.7},
            {"color": "red", "value": 0.9},
        ],
    )); pid += 1; y += 4

    # ================================================================
    # Section 2: E2E 시간 분해 (핵심 진단)
    # ================================================================
    panels.append(_row(pid, "⚡ E2E 시간 분해 (핵심 진단)", y)); pid += 1; y += 1

    # E2E Decomposition: stacked(queue+prefill+decode) + overlay(E2E)
    e2e_overrides = [{
        "matcher": {"id": "byName", "options": "E2E 전체 (p90)"},
        "properties": [
            {"id": "custom.stacking", "value": {"mode": "none"}},
            {"id": "custom.fillOpacity", "value": 0},
            {"id": "custom.lineWidth", "value": 3},
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}},
            {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 5]}},
        ],
    }]
    panels.append(_ts_panel(pid, "E2E 지연시간 분해 (p90)",
        "쌓인 영역(큐 대기 + 프리필 + 디코드)과 빨간 점선(E2E 전체)의 차이가\n"
        "'phantom time' — 메트릭에 잡히지 않는 소요 시간.\n\n"
        "판정 기준:\n"
        "· gap < 1초: 정상. 시간 성분이 잘 맞음\n"
        "· gap 10~30초: 엔진 내부 대기 (chunked prefill 청크 사이 등)\n"
        "· gap > 30초: 엔진 외부 문제 의심 → 'Inference vs E2E' 패널 확인",
        [
            _target(f"histogram_quantile(0.9, sum(rate(vllm:request_queue_time_seconds_bucket{f}[{iv}])) by (le))",
                    "큐 대기 (p90)", "A"),
            _target(f"histogram_quantile(0.9, sum(rate(vllm:request_prefill_time_seconds_bucket{f}[{iv}])) by (le))",
                    "프리필 연산 (p90)", "B"),
            _target(f"histogram_quantile(0.9, sum(rate(vllm:request_decode_time_seconds_bucket{f}[{iv}])) by (le))",
                    "디코드 연산 (p90)", "C"),
            _target(f"histogram_quantile(0.9, sum(rate(vllm:e2e_request_latency_seconds_bucket{f}[{iv}])) by (le))",
                    "E2E 전체 (p90)", "D"),
        ],
        {"h": 10, "w": 24, "x": 0, "y": y},
        stacking=True, fill=30, overrides=e2e_overrides,
    )); pid += 1; y += 10

    # ================================================================
    # Section 3: 요청 특성 분석
    # ================================================================
    panels.append(_row(pid, "요청 특성 분석", y)); pid += 1; y += 1

    # 프롬프트 토큰 수 분포
    panels.append(_ts_panel(pid, "프롬프트 토큰 수 분포",
        "요청당 프롬프트(입력) 토큰 수의 분포.\n\n"
        "판정 기준:\n"
        "· p50 vs p99 격차 10배 이상 → 롱테일 존재\n"
        "  → p90 TTFT가 긴 프롬프트 요청들에 의해 끌어올려진 것\n"
        "· p99 > 50k → 롱테일이 TTFT 악화의 주범\n"
        "· p99 < 10k → 롱테일 아님, 다른 원인",
        [
            _target(f"histogram_quantile(0.5,  sum(rate(vllm:request_prompt_tokens_bucket{f}[5m])) by (le))",
                    "중앙값 (p50)", "A"),
            _target(f"histogram_quantile(0.9,  sum(rate(vllm:request_prompt_tokens_bucket{f}[5m])) by (le))",
                    "p90", "B"),
            _target(f"histogram_quantile(0.99, sum(rate(vllm:request_prompt_tokens_bucket{f}[5m])) by (le))",
                    "p99", "C"),
            _target(f"histogram_quantile(1.0,  sum(rate(vllm:request_prompt_tokens_bucket{f}[5m])) by (le))",
                    "최대값 (max)", "D"),
        ],
        {"h": 8, "w": 12, "x": 0, "y": y},
        unit="none",
    )); pid += 1

    # 이터레이션당 처리 토큰 수
    panels.append(_ts_panel(pid, "이터레이션당 처리 토큰 수",
        "스케줄러 1회 실행(iteration)에서 처리하는 토큰 수.\n"
        "Chunked prefill의 청크 크기를 간접 반영.\n\n"
        "판정 기준:\n"
        "· p90 ≈ 2048 → 기본 청크 크기 사용 중\n"
        "· --max-num-batched-tokens를 16384로 올리면 이 값도 증가해야 함\n"
        "· 너무 작으면 스케줄링 오버헤드 누적",
        [
            _target(f"histogram_quantile(0.5,  sum(rate(vllm:iteration_tokens_total_bucket{f}[{iv}])) by (le))",
                    "중앙값 (p50)", "A"),
            _target(f"histogram_quantile(0.9,  sum(rate(vllm:iteration_tokens_total_bucket{f}[{iv}])) by (le))",
                    "p90", "B"),
            _target(f"histogram_quantile(0.99, sum(rate(vllm:iteration_tokens_total_bucket{f}[{iv}])) by (le))",
                    "p99", "C"),
        ],
        {"h": 8, "w": 12, "x": 12, "y": y},
        unit="none",
    )); pid += 1; y += 8

    # ================================================================
    # Section 4: 동시성 & 자원 상태
    # ================================================================
    panels.append(_row(pid, "동시성 & 자원 상태", y)); pid += 1; y += 1

    # 동시 요청 수 (Running/Waiting/Swapped)
    panels.append(_ts_panel(pid, "동시 요청 수 (실행/대기/스왑)",
        "실행 중, 대기 중, 스왑된 요청 수의 시계열.\n\n"
        "판정 기준:\n"
        "· waiting 쌓이는데 Queue Wait이 10us → 메트릭 정의 불일치\n"
        "· swapped ≠ 0 → CPU 스왑 발생 (preemption 카운터에 안 잡힘)",
        [
            _target(f"sum(vllm:num_requests_running{f})", "실행 중", "A"),
            _target(f"sum(vllm:num_requests_waiting{f})", "대기 중", "B"),
            _target(f"sum(vllm:num_requests_swapped{f})", "스왑됨", "C"),
        ],
        {"h": 8, "w": 8, "x": 0, "y": y},
        unit="none", stacking=True, fill=30,
    )); pid += 1

    # KV Cache 사용률 추이 (GPU + CPU)
    panels.append(_ts_panel(pid, "KV Cache 사용률 추이",
        "GPU 및 CPU KV Cache 점유율 변화.\n\n"
        "판정 기준:\n"
        "· GPU > 90% 지속 + waiting 쌓임 → 메모리 병목\n"
        "  → FP8 전환 또는 max_model_len 축소 고려\n"
        "· waiting 0 + KV < 70% → 리소스 여유, 튜닝 이슈 아님",
        [
            _target(f"vllm:gpu_cache_usage_perc{f}", "GPU KV Cache"),
            _target(f"vllm:cpu_cache_usage_perc{f}", "CPU KV Cache", "B"),
        ],
        {"h": 8, "w": 8, "x": 8, "y": y},
        unit="percentunit", ymin=0, ymax=1,
        thresholds=[
            {"color": "green", "value": None},
            {"color": "orange", "value": 0.7},
            {"color": "red", "value": 0.9},
        ],
    )); pid += 1

    # Preemption 발생률
    panels.append(_ts_panel(pid, "Preemption 발생률",
        "Preemption(요청 중단 후 재계산) 발생 빈도.\n\n"
        "판정 기준:\n"
        "· 0 유지 → preemption이 원인은 아님\n"
        "· 간헐적 스파이크 → KV 압박 시 발생\n"
        "· rate = 초당 횟수, increase = 5분 누적",
        [
            _target(f"rate(vllm:num_preemptions_total{f}[{iv}])", "Preemption/초", "A"),
            _target(f"increase(vllm:num_preemptions_total{f}[5m])", "5분간 누적", "B"),
        ],
        {"h": 8, "w": 8, "x": 16, "y": y},
        unit="none",
    )); pid += 1; y += 8

    # ================================================================
    # Section 5: 처리량 & 병목 분리
    # ================================================================
    panels.append(_row(pid, "처리량 & 병목 분리", y)); pid += 1; y += 1

    # 토큰 처리량
    panels.append(_ts_panel(pid, "토큰 처리량 (tokens/s)",
        "초당 처리하는 토큰 수.\n\n"
        "· 입력(prefill) = 프롬프트 토큰 처리 속도\n"
        "· 생성(decode) = 새 토큰 생성 속도\n\n"
        "판정 기준:\n"
        "· prefill < 1000 tok/s → GPU 포화\n"
        "· 정상 범위인데 느림 → 파이프라인(스케줄링) 병목",
        [
            _target(f"sum(rate(vllm:prompt_tokens_total{f}[{iv}]))", "입력 토큰/초 (prefill)", "A"),
            _target(f"sum(rate(vllm:generation_tokens_total{f}[{iv}]))", "생성 토큰/초 (decode)", "B"),
        ],
        {"h": 8, "w": 12, "x": 0, "y": y},
        unit="short",
    )); pid += 1

    # Inference vs E2E Gap
    panels.append(_ts_panel(pid, "추론 시간 vs E2E (병목 분리)",
        "vLLM 엔진 내부 추론 시간과 E2E 전체 시간 비교.\n"
        "두 선의 차이 = 엔진 밖에서 소모되는 시간.\n"
        "(API server, 토크나이저, 네트워크, detokenize 등)\n\n"
        "판정 기준:\n"
        "· 차이 작음 → vLLM 내부 문제\n"
        "· 차이 50초+ → vLLM 밖(Dify API layer 등) 병목",
        [
            _target(f"histogram_quantile(0.9, sum(rate(vllm:request_inference_time_seconds_bucket{f}[{iv}])) by (le))",
                    "추론 시간 (p90)", "A"),
            _target(f"histogram_quantile(0.9, sum(rate(vllm:e2e_request_latency_seconds_bucket{f}[{iv}])) by (le))",
                    "E2E 전체 (p90)", "B"),
        ],
        {"h": 8, "w": 12, "x": 12, "y": y},
    )); pid += 1; y += 8

    # ================================================================
    # Section 6: 분포 분석
    # ================================================================
    panels.append(_row(pid, "분포 분석", y)); pid += 1; y += 1

    # TTFT 히트맵
    panels.append({
        "id": pid, "title": "TTFT 분포 히트맵",
        "description": (
            "TTFT의 실제 분포를 시간축으로 표시.\n\n"
            "판정 기준:\n"
            "· 이중 분포(bimodal) → 요청 유형이 2종류 (짧은/긴)\n"
            "· 특정 시간대에 상위 버킷 채워짐 → 트래픽 피크 시 악화\n"
            "· 색이 진한 영역 = 대부분의 요청이 걸리는 시간대"
        ),
        "type": "heatmap", "datasource": _ds(),
        "targets": [_target(
            f"sum(increase(vllm:time_to_first_token_seconds_bucket{f}[{iv}])) by (le)",
            "{{le}}", "A", fmt="heatmap",
        )],
        "gridPos": {"h": 8, "w": 16, "x": 0, "y": y},
        "options": {
            "calculate": False,
            "yAxis": {"unit": "s"},
            "color": {"scheme": "Spectral", "reverse": True},
            "cellGap": 1,
        },
    }); pid += 1

    # 요청 성공률
    panels.append(_ts_panel(pid, "요청 성공률",
        "초당 완료된 요청 수.\n\n"
        "· 요청 실패/타임아웃이 있으면 레이턴시 분포를 왜곡\n"
        "· 급격한 하락 → 서버 장애 또는 OOM 의심",
        [_target(f"sum(rate(vllm:request_success_total{f}[{iv}]))", "성공 요청/초", "A")],
        {"h": 8, "w": 8, "x": 16, "y": y},
        unit="reqps",
    )); pid += 1

    return panels
