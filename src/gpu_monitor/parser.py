"""Prometheus 텍스트 형식 메트릭을 파싱하여 구조화된 데이터로 변환."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from prometheus_client.parser import text_string_to_metric_families


@dataclass
class GpuMetric:
    timestamp: float
    host: str
    gpu_id: str
    metric_name: str
    value: float
    labels: Dict[str, str]


# DCGM exporter가 내보내는 주요 메트릭
METRIC_ALLOWLIST = {
    "DCGM_FI_DEV_GPU_UTIL",           # GPU 활용률 (%)
    "DCGM_FI_DEV_MEM_COPY_UTIL",      # Memory BW 활용률 (%)
    "DCGM_FI_DEV_FB_USED",            # Framebuffer(VRAM) 사용량 (MiB)
    "DCGM_FI_DEV_FB_FREE",            # Framebuffer 여유 (MiB)
    "DCGM_FI_DEV_GPU_TEMP",           # GPU 온도 (°C)
    "DCGM_FI_DEV_POWER_USAGE",        # 전력 사용량 (W)
    "DCGM_FI_PROF_GR_ENGINE_ACTIVE",  # Graphics Engine Active (비율)
    "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE",# Tensor Core Active (비율)
    "DCGM_FI_PROF_DRAM_ACTIVE",       # DRAM Active (비율)
    "DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL",  # NVLink 대역폭
    "DCGM_FI_DEV_PCIE_TX_THROUGHPUT",      # PCIe TX
    "DCGM_FI_DEV_PCIE_RX_THROUGHPUT",      # PCIe RX
}


def parse_prometheus_text(
    text: str,
    host: str,
    timestamp: Optional[float] = None,
    allowlist: Optional[set] = None,
) -> List[GpuMetric]:
    """Prometheus 텍스트 형식을 GpuMetric 리스트로 파싱.

    Args:
        text: Prometheus exposition format 텍스트
        host: 수집 대상 호스트명
        timestamp: 타임스탬프 (None이면 현재 시각)
        allowlist: 수집할 메트릭 이름 집합 (None이면 METRIC_ALLOWLIST 사용)
    """
    if timestamp is None:
        timestamp = time.time()
    if allowlist is None:
        allowlist = METRIC_ALLOWLIST

    metrics: List[GpuMetric] = []

    for family in text_string_to_metric_families(text):
        if family.name not in allowlist:
            continue

        for sample in family.samples:
            labels = dict(sample.labels)
            gpu_id = labels.get("gpu", labels.get("GPU_I_ID", "0"))
            # Hostname 라벨이 있으면 사용, 없으면 인자로 받은 host 사용
            effective_host = labels.get("Hostname", host)

            metrics.append(
                GpuMetric(
                    timestamp=timestamp,
                    host=effective_host,
                    gpu_id=gpu_id,
                    metric_name=sample.name,
                    value=float(sample.value),
                    labels=labels,
                )
            )

    return metrics
