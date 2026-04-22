"""리포트 생성 테스트."""

import sqlite3
import time

import pytest

from gpu_monitor.reporter import Reporter


@pytest.fixture
def recording_db(tmp_path):
    """테스트용 기록 DB 생성."""
    db_path = str(tmp_path / "test_recording.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE session_info (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL, host TEXT, gpu_id TEXT,
            metric_name TEXT, value REAL
        );
    """)

    start_time = time.time() - 60
    conn.executemany(
        "INSERT INTO session_info (key, value) VALUES (?, ?)",
        [
            ("session_id", "test_session"),
            ("label", "unit-test"),
            ("start_time", str(start_time)),
            ("end_time", str(start_time + 60)),
            ("interval_ms", "100"),
        ],
    )

    # 모의 데이터 삽입
    rows = []
    for i in range(100):
        ts = start_time + i * 0.6
        for gpu_id in ["0", "1"]:
            rows.append((ts, "vm-01", gpu_id, "DCGM_FI_DEV_GPU_UTIL", 50 + i * 0.3))
            rows.append((ts, "vm-01", gpu_id, "DCGM_FI_DEV_GPU_TEMP", 60 + i * 0.1))
            rows.append((ts, "vm-01", gpu_id, "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE", 0.4 + i * 0.003))
            rows.append((ts, "vm-01", gpu_id, "DCGM_FI_PROF_DRAM_ACTIVE", 0.3 + i * 0.002))

    conn.executemany(
        "INSERT INTO metrics (timestamp, host, gpu_id, metric_name, value) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


class TestReporter:
    def test_load_session(self, recording_db):
        reporter = Reporter()
        df = reporter.load_session(recording_db)
        assert len(df) > 0
        assert set(df.columns) == {"timestamp", "host", "gpu_id", "metric_name", "value"}

    def test_compute_stats(self, recording_db):
        reporter = Reporter()
        df = reporter.load_session(recording_db)
        stats = reporter.compute_stats(df)

        assert "mean" in stats.columns
        assert "p50" in stats.columns
        assert "p95" in stats.columns
        assert "p99" in stats.columns
        assert "max" in stats.columns
        assert len(stats) > 0

    def test_export_csv(self, recording_db, tmp_path):
        reporter = Reporter(output_dir=str(tmp_path / "reports"))
        df = reporter.load_session(recording_db)
        csv_path = reporter.export_csv(df, "test-export")

        from pathlib import Path
        assert Path(csv_path).exists()
        assert Path(csv_path).stat().st_size > 0

    def test_generate_summary(self, recording_db, tmp_path):
        reporter = Reporter(output_dir=str(tmp_path / "reports"))
        df = reporter.load_session(recording_db)
        stats = reporter.compute_stats(df)
        summary = reporter.generate_summary(stats, "test-summary", 60.0)

        assert "test-summary" in summary
        assert "60.0" in summary
        assert "DCGM_FI_DEV_GPU_UTIL" in summary

    def test_generate_charts(self, recording_db, tmp_path):
        reporter = Reporter(output_dir=str(tmp_path / "reports"))
        df = reporter.load_session(recording_db)
        chart_paths = reporter.generate_charts(df, "test-charts")

        from pathlib import Path
        assert len(chart_paths) > 0
        for p in chart_paths:
            assert Path(p).exists()

    def test_full_report(self, recording_db, tmp_path):
        reporter = Reporter(output_dir=str(tmp_path / "reports"))
        result = reporter.generate_report(recording_db)

        assert "summary" in result
        assert "csv_path" in result
        assert "chart_paths" in result
        assert "stats" in result
        assert len(result["summary"]) > 0

    def test_empty_dataframe(self, tmp_path):
        reporter = Reporter(output_dir=str(tmp_path / "reports"))
        import pandas as pd
        stats = reporter.compute_stats(pd.DataFrame())
        assert stats.empty
