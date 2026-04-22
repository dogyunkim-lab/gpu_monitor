"""공통 테스트 fixture."""

import os
import sys
import tempfile

import pytest

# src/ 를 import path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gpu_monitor.config import AppConfig, VMConfig, CollectorConfig, StorageConfig, AlertConfig, RecorderConfig, WebConfig


SAMPLE_PROMETHEUS_TEXT = """\
# HELP DCGM_FI_DEV_GPU_UTIL GPU utilization (in %).
# TYPE DCGM_FI_DEV_GPU_UTIL gauge
DCGM_FI_DEV_GPU_UTIL{gpu="0",UUID="GPU-aaaa",device="nvidia0",Hostname="gpu-vm-01"} 75
DCGM_FI_DEV_GPU_UTIL{gpu="1",UUID="GPU-bbbb",device="nvidia1",Hostname="gpu-vm-01"} 82
# HELP DCGM_FI_DEV_MEM_COPY_UTIL Memory utilization (in %).
# TYPE DCGM_FI_DEV_MEM_COPY_UTIL gauge
DCGM_FI_DEV_MEM_COPY_UTIL{gpu="0",UUID="GPU-aaaa",device="nvidia0",Hostname="gpu-vm-01"} 45
DCGM_FI_DEV_MEM_COPY_UTIL{gpu="1",UUID="GPU-bbbb",device="nvidia1",Hostname="gpu-vm-01"} 60
# HELP DCGM_FI_DEV_GPU_TEMP GPU temperature (in C).
# TYPE DCGM_FI_DEV_GPU_TEMP gauge
DCGM_FI_DEV_GPU_TEMP{gpu="0",UUID="GPU-aaaa",device="nvidia0",Hostname="gpu-vm-01"} 65
DCGM_FI_DEV_GPU_TEMP{gpu="1",UUID="GPU-bbbb",device="nvidia1",Hostname="gpu-vm-01"} 72
# HELP DCGM_FI_DEV_FB_USED Framebuffer memory used (in MiB).
# TYPE DCGM_FI_DEV_FB_USED gauge
DCGM_FI_DEV_FB_USED{gpu="0",UUID="GPU-aaaa",device="nvidia0",Hostname="gpu-vm-01"} 40960
DCGM_FI_DEV_FB_USED{gpu="1",UUID="GPU-bbbb",device="nvidia1",Hostname="gpu-vm-01"} 65536
# HELP DCGM_FI_DEV_FB_FREE Framebuffer memory free (in MiB).
# TYPE DCGM_FI_DEV_FB_FREE gauge
DCGM_FI_DEV_FB_FREE{gpu="0",UUID="GPU-aaaa",device="nvidia0",Hostname="gpu-vm-01"} 40960
DCGM_FI_DEV_FB_FREE{gpu="1",UUID="GPU-bbbb",device="nvidia1",Hostname="gpu-vm-01"} 16384
# HELP DCGM_FI_DEV_POWER_USAGE Power draw (in W).
# TYPE DCGM_FI_DEV_POWER_USAGE gauge
DCGM_FI_DEV_POWER_USAGE{gpu="0",UUID="GPU-aaaa",device="nvidia0",Hostname="gpu-vm-01"} 250
DCGM_FI_DEV_POWER_USAGE{gpu="1",UUID="GPU-bbbb",device="nvidia1",Hostname="gpu-vm-01"} 310
# HELP DCGM_FI_PROF_PIPE_TENSOR_ACTIVE Ratio of cycles the tensor (HMMA) pipe is active.
# TYPE DCGM_FI_PROF_PIPE_TENSOR_ACTIVE gauge
DCGM_FI_PROF_PIPE_TENSOR_ACTIVE{gpu="0",UUID="GPU-aaaa",device="nvidia0",Hostname="gpu-vm-01"} 0.55
DCGM_FI_PROF_PIPE_TENSOR_ACTIVE{gpu="1",UUID="GPU-bbbb",device="nvidia1",Hostname="gpu-vm-01"} 0.78
# HELP DCGM_FI_PROF_DRAM_ACTIVE Ratio of cycles the device memory interface is active.
# TYPE DCGM_FI_PROF_DRAM_ACTIVE gauge
DCGM_FI_PROF_DRAM_ACTIVE{gpu="0",UUID="GPU-aaaa",device="nvidia0",Hostname="gpu-vm-01"} 0.30
DCGM_FI_PROF_DRAM_ACTIVE{gpu="1",UUID="GPU-bbbb",device="nvidia1",Hostname="gpu-vm-01"} 0.62
"""


@pytest.fixture
def sample_prometheus_text():
    return SAMPLE_PROMETHEUS_TEXT


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_metrics.db")


@pytest.fixture
def sample_config(tmp_path):
    return AppConfig(
        vms=[
            VMConfig(host="127.0.0.1", port=19400, name="test-vm-01"),
        ],
        collector=CollectorConfig(timeout_seconds=1.0, max_consecutive_failures=2),
        storage=StorageConfig(db_path=str(tmp_path / "test.db"), retention_days=1),
        recorder=RecorderConfig(interval_ms=500, output_dir=str(tmp_path / "recordings")),
        alerts=AlertConfig(
            gpu_util_threshold=90.0,
            gpu_util_duration_seconds=3,
            temperature_threshold=70.0,
            vram_util_threshold=80.0,
            log_file=str(tmp_path / "test_alerts.log"),
        ),
        web=WebConfig(port=15555),
    )
