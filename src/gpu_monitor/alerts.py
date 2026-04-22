"""GPU 알림 로직 — 과부하, 고온, VRAM 경고 감지."""

from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from gpu_monitor.config import AlertConfig
from gpu_monitor.parser import GpuMetric

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    alert_type: str  # "gpu_util", "temperature", "vram_util"
    host: str
    gpu_id: str
    value: float
    threshold: float
    message: str
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False
    resolved_at: Optional[float] = None


class AlertManager:
    """실시간 알림 관리자."""

    def __init__(self, config: AlertConfig):
        self.config = config
        self._active_alerts: List[Alert] = []
        self._alert_history: List[Alert] = []
        self._lock = threading.Lock()

        # GPU 사용률 지속 시간 추적: (host, gpu_id) → 초과 시작 타임스탬프
        self._gpu_util_start: Dict[Tuple[str, str], float] = {}
        # 이미 발생한 알림 추적 (중복 방지)
        self._active_keys: set = set()

        # 알림 로그 파일 설정
        self._alert_logger = logging.getLogger("gpu_monitor.alerts.file")
        if config.log_file:
            handler = logging.FileHandler(config.log_file)
            handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
            self._alert_logger.addHandler(handler)
            self._alert_logger.setLevel(logging.WARNING)

    def process_metrics(self, metrics: List[GpuMetric]):
        """수집된 메트릭으로 알림 조건 확인."""
        for m in metrics:
            if m.metric_name == "DCGM_FI_DEV_GPU_UTIL":
                self._check_gpu_util(m)
            elif m.metric_name == "DCGM_FI_DEV_GPU_TEMP":
                self._check_temperature(m)
            elif m.metric_name == "DCGM_FI_DEV_FB_USED":
                # VRAM 사용률은 used/(used+free)로 계산해야 하지만
                # 단일 메트릭으로는 계산 불가 → 별도 처리 필요
                pass

        # VRAM 사용률 계산 (used + free 메트릭 조합)
        self._check_vram_util(metrics)

    def _check_gpu_util(self, m: GpuMetric):
        key = (m.host, m.gpu_id)
        alert_key = f"gpu_util:{m.host}:{m.gpu_id}"

        if m.value >= self.config.gpu_util_threshold:
            if key not in self._gpu_util_start:
                self._gpu_util_start[key] = m.timestamp

            elapsed = m.timestamp - self._gpu_util_start[key]
            if elapsed >= self.config.gpu_util_duration_seconds and alert_key not in self._active_keys:
                self._fire_alert(Alert(
                    alert_type="gpu_util",
                    host=m.host,
                    gpu_id=m.gpu_id,
                    value=m.value,
                    threshold=self.config.gpu_util_threshold,
                    message=f"GPU 사용률 {m.value:.1f}% >= {self.config.gpu_util_threshold}% ({elapsed:.0f}초 지속) — {m.host} GPU {m.gpu_id}",
                    timestamp=m.timestamp,
                ))
                self._active_keys.add(alert_key)
        else:
            self._gpu_util_start.pop(key, None)
            if alert_key in self._active_keys:
                self._resolve_alert(alert_key)

    def _check_temperature(self, m: GpuMetric):
        alert_key = f"temperature:{m.host}:{m.gpu_id}"

        if m.value >= self.config.temperature_threshold:
            if alert_key not in self._active_keys:
                self._fire_alert(Alert(
                    alert_type="temperature",
                    host=m.host,
                    gpu_id=m.gpu_id,
                    value=m.value,
                    threshold=self.config.temperature_threshold,
                    message=f"GPU 온도 {m.value:.0f}°C >= {self.config.temperature_threshold}°C — {m.host} GPU {m.gpu_id}",
                    timestamp=m.timestamp,
                ))
                self._active_keys.add(alert_key)
        elif alert_key in self._active_keys:
            self._resolve_alert(alert_key)

    def _check_vram_util(self, metrics: List[GpuMetric]):
        # (host, gpu_id) → {used, free}
        vram: Dict[Tuple[str, str], Dict[str, float]] = {}
        for m in metrics:
            key = (m.host, m.gpu_id)
            if m.metric_name == "DCGM_FI_DEV_FB_USED":
                vram.setdefault(key, {})["used"] = m.value
            elif m.metric_name == "DCGM_FI_DEV_FB_FREE":
                vram.setdefault(key, {})["free"] = m.value

        for (host, gpu_id), vals in vram.items():
            if "used" in vals and "free" in vals:
                total = vals["used"] + vals["free"]
                if total <= 0:
                    continue
                util_pct = (vals["used"] / total) * 100
                alert_key = f"vram_util:{host}:{gpu_id}"

                if util_pct >= self.config.vram_util_threshold:
                    if alert_key not in self._active_keys:
                        self._fire_alert(Alert(
                            alert_type="vram_util",
                            host=host,
                            gpu_id=gpu_id,
                            value=util_pct,
                            threshold=self.config.vram_util_threshold,
                            message=f"VRAM 사용률 {util_pct:.1f}% >= {self.config.vram_util_threshold}% — {host} GPU {gpu_id}",
                        ))
                        self._active_keys.add(alert_key)
                elif alert_key in self._active_keys:
                    self._resolve_alert(alert_key)

    def _fire_alert(self, alert: Alert):
        with self._lock:
            self._active_alerts.append(alert)
            self._alert_history.append(alert)
        self._alert_logger.warning(alert.message)
        logger.warning("ALERT: %s", alert.message)

    def _resolve_alert(self, alert_key: str):
        self._active_keys.discard(alert_key)
        now = time.time()
        with self._lock:
            for a in self._active_alerts:
                key = f"{a.alert_type}:{a.host}:{a.gpu_id}"
                if key == alert_key and not a.resolved:
                    a.resolved = True
                    a.resolved_at = now
            self._active_alerts = [a for a in self._active_alerts if not a.resolved]

    def get_active_alerts(self) -> List[Dict]:
        """활성 알림 목록 반환."""
        with self._lock:
            return [
                {
                    "type": a.alert_type,
                    "host": a.host,
                    "gpu_id": a.gpu_id,
                    "value": a.value,
                    "threshold": a.threshold,
                    "message": a.message,
                    "timestamp": a.timestamp,
                }
                for a in self._active_alerts
            ]

    def get_alert_history(self, limit: int = 100) -> List[Dict]:
        """알림 히스토리 반환."""
        with self._lock:
            return [
                {
                    "type": a.alert_type,
                    "host": a.host,
                    "gpu_id": a.gpu_id,
                    "value": a.value,
                    "threshold": a.threshold,
                    "message": a.message,
                    "timestamp": a.timestamp,
                    "resolved": a.resolved,
                    "resolved_at": a.resolved_at,
                }
                for a in self._alert_history[-limit:]
            ]
