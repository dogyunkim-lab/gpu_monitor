"""Prometheus 메트릭 파싱 테스트."""

import time

from gpu_monitor.parser import parse_prometheus_text, METRIC_ALLOWLIST


class TestParsePrometheusText:
    def test_basic_parsing(self, sample_prometheus_text):
        metrics = parse_prometheus_text(sample_prometheus_text, host="test-host")
        assert len(metrics) > 0

    def test_gpu_ids_extracted(self, sample_prometheus_text):
        metrics = parse_prometheus_text(sample_prometheus_text, host="test-host")
        gpu_ids = {m.gpu_id for m in metrics}
        assert "0" in gpu_ids
        assert "1" in gpu_ids

    def test_hostname_from_labels(self, sample_prometheus_text):
        metrics = parse_prometheus_text(sample_prometheus_text, host="fallback-host")
        # Hostname 라벨이 있으므로 "gpu-vm-01" 사용
        hosts = {m.host for m in metrics}
        assert "gpu-vm-01" in hosts

    def test_hostname_fallback(self):
        text = """\
# HELP DCGM_FI_DEV_GPU_UTIL GPU utilization.
# TYPE DCGM_FI_DEV_GPU_UTIL gauge
DCGM_FI_DEV_GPU_UTIL{gpu="0"} 50
"""
        metrics = parse_prometheus_text(text, host="my-host")
        assert metrics[0].host == "my-host"

    def test_metric_names_in_allowlist(self, sample_prometheus_text):
        metrics = parse_prometheus_text(sample_prometheus_text, host="test-host")
        for m in metrics:
            assert m.metric_name in METRIC_ALLOWLIST

    def test_custom_timestamp(self, sample_prometheus_text):
        ts = 1700000000.0
        metrics = parse_prometheus_text(sample_prometheus_text, host="test-host", timestamp=ts)
        for m in metrics:
            assert m.timestamp == ts

    def test_values_are_floats(self, sample_prometheus_text):
        metrics = parse_prometheus_text(sample_prometheus_text, host="test-host")
        for m in metrics:
            assert isinstance(m.value, float)

    def test_custom_allowlist(self, sample_prometheus_text):
        metrics = parse_prometheus_text(
            sample_prometheus_text,
            host="test-host",
            allowlist={"DCGM_FI_DEV_GPU_UTIL"},
        )
        assert all(m.metric_name == "DCGM_FI_DEV_GPU_UTIL" for m in metrics)

    def test_empty_text(self):
        metrics = parse_prometheus_text("", host="test-host")
        assert metrics == []

    def test_expected_metric_count(self, sample_prometheus_text):
        metrics = parse_prometheus_text(sample_prometheus_text, host="test-host")
        # 8 metrics × 2 GPUs = 16
        assert len(metrics) == 16
