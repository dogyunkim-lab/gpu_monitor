"""Flask 웹 대시보드 서버."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from flask import Flask, jsonify, render_template, request

if TYPE_CHECKING:
    from gpu_monitor.alerts import AlertManager
    from gpu_monitor.collector import MetricCollector
    from gpu_monitor.recorder import Recorder
    from gpu_monitor.storage import MetricStorage

logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)

# 전역 참조 (CLI에서 주입)
_storage: MetricStorage = None  # type: ignore
_collector: MetricCollector = None  # type: ignore
_alert_manager: AlertManager = None  # type: ignore
_recorder: Recorder = None  # type: ignore


def init_app(
    storage: MetricStorage,
    collector: MetricCollector,
    alert_manager: AlertManager,
    recorder: Recorder,
) -> Flask:
    global _storage, _collector, _alert_manager, _recorder
    _storage = storage
    _collector = collector
    _alert_manager = alert_manager
    _recorder = recorder
    return app


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/current")
def api_current():
    """현재 10 GPU 상태 JSON."""
    latest = _storage.get_latest()

    # (host, gpu_id) 기준으로 그룹핑
    gpus = {}
    for m in latest:
        key = f"{m['host']}:{m['gpu_id']}"
        if key not in gpus:
            gpus[key] = {
                "host": m["host"],
                "gpu_id": m["gpu_id"],
                "metrics": {},
                "timestamp": m["timestamp"],
            }
        gpus[key]["metrics"][m["metric_name"]] = m["value"]

    # VM 상태 추가
    vm_statuses = {}
    if _collector:
        for host, status in _collector.get_vm_statuses().items():
            vm_statuses[status.name] = {
                "is_up": status.is_up,
                "consecutive_failures": status.consecutive_failures,
                "last_success": status.last_success,
            }

    return jsonify({
        "gpus": list(gpus.values()),
        "vm_statuses": vm_statuses,
    })


@app.route("/api/history")
def api_history():
    """최근 시계열 데이터."""
    minutes = request.args.get("minutes", 5, type=int)
    data = _storage.get_recent(minutes=minutes)
    return jsonify({"data": data, "minutes": minutes})


@app.route("/api/alerts")
def api_alerts():
    """활성 알림 목록."""
    active = _alert_manager.get_active_alerts() if _alert_manager else []
    history = _alert_manager.get_alert_history(limit=50) if _alert_manager else []
    return jsonify({"active": active, "history": history})


@app.route("/api/recording/status")
def api_recording_status():
    """기록 상태."""
    if _recorder and _recorder.is_recording:
        session = _recorder.current_session
        return jsonify({
            "recording": True,
            "session_id": session.session_id if session else None,
            "label": session.label if session else None,
        })
    return jsonify({"recording": False})
