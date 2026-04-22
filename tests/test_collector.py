"""Mock HTTP 서버로 수집 테스트."""

import http.server
import threading
import time

import pytest

from gpu_monitor.config import AppConfig, VMConfig, CollectorConfig, StorageConfig
from gpu_monitor.collector import MetricCollector
from gpu_monitor.storage import MetricStorage

SAMPLE_PROMETHEUS_TEXT = """\
# HELP DCGM_FI_DEV_GPU_UTIL GPU utilization (in %).
# TYPE DCGM_FI_DEV_GPU_UTIL gauge
DCGM_FI_DEV_GPU_UTIL{gpu="0",UUID="GPU-aaaa",device="nvidia0",Hostname="gpu-vm-01"} 75
DCGM_FI_DEV_GPU_UTIL{gpu="1",UUID="GPU-bbbb",device="nvidia1",Hostname="gpu-vm-01"} 82
# HELP DCGM_FI_DEV_GPU_TEMP GPU temperature (in C).
# TYPE DCGM_FI_DEV_GPU_TEMP gauge
DCGM_FI_DEV_GPU_TEMP{gpu="0",UUID="GPU-aaaa",device="nvidia0",Hostname="gpu-vm-01"} 65
DCGM_FI_DEV_GPU_TEMP{gpu="1",UUID="GPU-bbbb",device="nvidia1",Hostname="gpu-vm-01"} 72
"""


class MockDCGMHandler(http.server.BaseHTTPRequestHandler):
    """DCGM exporter를 모방하는 Mock HTTP 핸들러."""

    response_text = SAMPLE_PROMETHEUS_TEXT
    should_fail = False

    def do_GET(self):
        if self.should_fail:
            self.send_error(500, "Internal Server Error")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(self.response_text.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # 로그 숨김


@pytest.fixture
def mock_server():
    """Mock DCGM exporter HTTP 서버."""
    server = http.server.HTTPServer(("127.0.0.1", 0), MockDCGMHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, port
    server.shutdown()


class TestMetricCollector:
    def test_scrape_single_vm(self, mock_server, tmp_path):
        server, port = mock_server
        config = AppConfig(
            vms=[VMConfig(host="127.0.0.1", port=port, name="test-vm")],
            collector=CollectorConfig(timeout_seconds=2.0),
            storage=StorageConfig(db_path=str(tmp_path / "test.db")),
        )
        storage = MetricStorage(db_path=config.storage.db_path)
        collector = MetricCollector(config=config, storage=storage)

        metrics = collector.scrape_vm(config.vms[0])
        assert len(metrics) > 0
        storage.close()

    def test_collect_all(self, mock_server, tmp_path):
        server, port = mock_server
        config = AppConfig(
            vms=[VMConfig(host="127.0.0.1", port=port, name="test-vm")],
            collector=CollectorConfig(timeout_seconds=2.0),
            storage=StorageConfig(db_path=str(tmp_path / "test.db")),
        )
        storage = MetricStorage(db_path=config.storage.db_path)
        collector = MetricCollector(config=config, storage=storage)

        metrics = collector.collect_all()
        assert len(metrics) > 0

        # DB에 저장되었는지 확인
        latest = storage.get_latest()
        assert len(latest) > 0
        storage.close()

    def test_vm_down_detection(self, tmp_path):
        """연결 불가 VM은 down으로 표시."""
        config = AppConfig(
            vms=[VMConfig(host="127.0.0.1", port=19999, name="dead-vm")],
            collector=CollectorConfig(timeout_seconds=0.5, max_consecutive_failures=2),
            storage=StorageConfig(db_path=str(tmp_path / "test.db")),
        )
        storage = MetricStorage(db_path=config.storage.db_path)
        collector = MetricCollector(config=config, storage=storage)

        # 2회 연속 실패 → down
        collector.collect_all()
        collector.collect_all()

        statuses = collector.get_vm_statuses()
        assert statuses["127.0.0.1"].is_up is False
        assert statuses["127.0.0.1"].consecutive_failures >= 2
        storage.close()

    def test_independent_failure_handling(self, mock_server, tmp_path):
        """하나의 VM 실패가 다른 VM에 영향 안줌."""
        server, port = mock_server
        config = AppConfig(
            vms=[
                VMConfig(host="127.0.0.1", port=port, name="good-vm"),
                VMConfig(host="127.0.0.1", port=19999, name="bad-vm"),
            ],
            collector=CollectorConfig(timeout_seconds=0.5),
            storage=StorageConfig(db_path=str(tmp_path / "test.db")),
        )
        storage = MetricStorage(db_path=config.storage.db_path)
        collector = MetricCollector(config=config, storage=storage)

        metrics = collector.collect_all()
        # good-vm에서 메트릭 수집 성공
        assert len(metrics) > 0
        storage.close()

    def test_background_collection(self, mock_server, tmp_path):
        """백그라운드 수집 시작/중지."""
        server, port = mock_server
        config = AppConfig(
            vms=[VMConfig(host="127.0.0.1", port=port, name="test-vm")],
            collector=CollectorConfig(timeout_seconds=2.0, interval_seconds=0.5),
            storage=StorageConfig(db_path=str(tmp_path / "test.db")),
        )
        storage = MetricStorage(db_path=config.storage.db_path)
        collector = MetricCollector(config=config, storage=storage)

        collector.start()
        assert collector.is_running
        time.sleep(1.5)
        collector.stop()
        assert not collector.is_running

        latest = storage.get_latest()
        assert len(latest) > 0
        storage.close()
