"""DCGM exporter 메트릭 수집기 — 단일 VM 및 멀티 VM 병렬 수집."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import httpx

from gpu_monitor.config import AppConfig, VMConfig
from gpu_monitor.parser import GpuMetric, parse_prometheus_text
from gpu_monitor.storage import MetricStorage

logger = logging.getLogger(__name__)


@dataclass
class VMStatus:
    host: str
    name: str
    is_up: bool = True
    consecutive_failures: int = 0
    last_success: Optional[float] = None
    last_error: Optional[str] = None


class MetricCollector:
    """멀티 VM 병렬 메트릭 수집기."""

    def __init__(
        self,
        config: AppConfig,
        storage: MetricStorage,
        on_metrics: Optional[Callable[[List[GpuMetric]], None]] = None,
    ):
        self.config = config
        self.storage = storage
        self.on_metrics = on_metrics  # 콜백 (알림 등에서 사용)

        self._vm_status: Dict[str, VMStatus] = {}
        for vm in config.vms:
            self._vm_status[vm.host] = VMStatus(host=vm.host, name=vm.name)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def scrape_vm(self, vm: VMConfig) -> List[GpuMetric]:
        """단일 VM에서 메트릭 스크레이핑."""
        ts = time.time()
        try:
            with httpx.Client(timeout=self.config.collector.timeout_seconds) as client:
                resp = client.get(vm.url)
                resp.raise_for_status()

            metrics = parse_prometheus_text(resp.text, host=vm.name, timestamp=ts)

            with self._lock:
                status = self._vm_status[vm.host]
                status.is_up = True
                status.consecutive_failures = 0
                status.last_success = ts

            return metrics

        except Exception as e:
            with self._lock:
                status = self._vm_status[vm.host]
                status.consecutive_failures += 1
                status.last_error = str(e)
                if status.consecutive_failures >= self.config.collector.max_consecutive_failures:
                    status.is_up = False

            logger.warning("VM %s 수집 실패 (%d회 연속): %s", vm.name, status.consecutive_failures, e)
            return []

    def collect_all(self) -> List[GpuMetric]:
        """모든 VM에서 병렬 수집."""
        all_metrics: List[GpuMetric] = []

        with ThreadPoolExecutor(max_workers=len(self.config.vms) or 1) as executor:
            futures = {
                executor.submit(self.scrape_vm, vm): vm
                for vm in self.config.vms
            }
            for future in as_completed(futures):
                metrics = future.result()
                all_metrics.extend(metrics)

        if all_metrics:
            self.storage.store_metrics(all_metrics)
            if self.on_metrics:
                self.on_metrics(all_metrics)

        return all_metrics

    def _collection_loop(self):
        """백그라운드 수집 루프."""
        logger.info("수집 시작 (간격: %.1fs)", self.config.collector.interval_seconds)
        while self._running:
            start = time.time()
            try:
                self.collect_all()
            except Exception:
                logger.exception("수집 루프 에러")

            elapsed = time.time() - start
            sleep_time = max(0, self.config.collector.interval_seconds - elapsed)
            if sleep_time > 0:
                # 짧은 간격으로 나눠서 중지 신호 확인
                end_time = time.time() + sleep_time
                while self._running and time.time() < end_time:
                    time.sleep(min(0.1, end_time - time.time()))

    def start(self):
        """백그라운드 수집 시작."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._thread.start()
        logger.info("Collector 시작됨")

    def stop(self):
        """백그라운드 수집 중지."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Collector 중지됨")

    def get_vm_statuses(self) -> Dict[str, VMStatus]:
        """모든 VM 상태 반환."""
        with self._lock:
            return dict(self._vm_status)

    @property
    def is_running(self) -> bool:
        return self._running
