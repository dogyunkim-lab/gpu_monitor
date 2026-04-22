"""기록 모드 테스트."""

import http.server
import threading
import time

import pytest

from gpu_monitor.config import AppConfig, VMConfig, CollectorConfig, StorageConfig, RecorderConfig
from gpu_monitor.collector import MetricCollector
from gpu_monitor.recorder import Recorder
from gpu_monitor.storage import MetricStorage

SAMPLE_PROMETHEUS_TEXT = """\
# HELP DCGM_FI_DEV_GPU_UTIL GPU utilization (in %).
# TYPE DCGM_FI_DEV_GPU_UTIL gauge
DCGM_FI_DEV_GPU_UTIL{gpu="0",UUID="GPU-aaaa",device="nvidia0",Hostname="gpu-vm-01"} 75
DCGM_FI_DEV_GPU_UTIL{gpu="1",UUID="GPU-bbbb",device="nvidia1",Hostname="gpu-vm-01"} 82
"""


class MockHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(SAMPLE_PROMETHEUS_TEXT.encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def mock_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()


class TestRecorder:
    def test_start_stop(self, mock_server, tmp_path):
        port = mock_server
        config = AppConfig(
            vms=[VMConfig(host="127.0.0.1", port=port, name="test-vm")],
            collector=CollectorConfig(timeout_seconds=2.0),
            storage=StorageConfig(db_path=str(tmp_path / "main.db")),
            recorder=RecorderConfig(interval_ms=200, output_dir=str(tmp_path / "rec")),
        )
        storage = MetricStorage(db_path=config.storage.db_path)
        collector = MetricCollector(config=config, storage=storage)
        recorder = Recorder(config=config, collector=collector)

        session = recorder.start(label="test-session")
        assert recorder.is_recording
        assert session.label == "test-session"

        time.sleep(1)
        session = recorder.stop()
        assert not recorder.is_recording
        assert session is not None
        assert session.end_time is not None
        assert session.end_time > session.start_time

        storage.close()

    def test_recording_creates_db(self, mock_server, tmp_path):
        port = mock_server
        config = AppConfig(
            vms=[VMConfig(host="127.0.0.1", port=port, name="test-vm")],
            collector=CollectorConfig(timeout_seconds=2.0),
            storage=StorageConfig(db_path=str(tmp_path / "main.db")),
            recorder=RecorderConfig(interval_ms=200, output_dir=str(tmp_path / "rec")),
        )
        storage = MetricStorage(db_path=config.storage.db_path)
        collector = MetricCollector(config=config, storage=storage)
        recorder = Recorder(config=config, collector=collector)

        recorder.start(label="db-test")
        time.sleep(0.8)
        session = recorder.stop()

        from pathlib import Path
        assert Path(session.db_path).exists()
        storage.close()

    def test_list_sessions(self, mock_server, tmp_path):
        port = mock_server
        config = AppConfig(
            vms=[VMConfig(host="127.0.0.1", port=port, name="test-vm")],
            collector=CollectorConfig(timeout_seconds=2.0),
            storage=StorageConfig(db_path=str(tmp_path / "main.db")),
            recorder=RecorderConfig(interval_ms=200, output_dir=str(tmp_path / "rec")),
        )
        storage = MetricStorage(db_path=config.storage.db_path)
        collector = MetricCollector(config=config, storage=storage)
        recorder = Recorder(config=config, collector=collector)

        recorder.start(label="session-1")
        time.sleep(0.5)
        recorder.stop()

        sessions = recorder.list_sessions()
        assert len(sessions) >= 1
        assert sessions[0]["label"] == "session-1"
        storage.close()

    def test_cannot_start_twice(self, mock_server, tmp_path):
        port = mock_server
        config = AppConfig(
            vms=[VMConfig(host="127.0.0.1", port=port, name="test-vm")],
            collector=CollectorConfig(timeout_seconds=2.0),
            storage=StorageConfig(db_path=str(tmp_path / "main.db")),
            recorder=RecorderConfig(interval_ms=200, output_dir=str(tmp_path / "rec")),
        )
        storage = MetricStorage(db_path=config.storage.db_path)
        collector = MetricCollector(config=config, storage=storage)
        recorder = Recorder(config=config, collector=collector)

        recorder.start(label="first")
        with pytest.raises(RuntimeError, match="이미 기록 중"):
            recorder.start(label="second")
        recorder.stop()
        storage.close()
