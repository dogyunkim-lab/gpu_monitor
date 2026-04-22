"""SQLite 저장/조회 테스트."""

import time

import pytest

from gpu_monitor.parser import GpuMetric
from gpu_monitor.storage import MetricStorage


@pytest.fixture
def storage(tmp_db):
    s = MetricStorage(db_path=tmp_db, retention_days=1)
    yield s
    s.close()


def make_metrics(host="vm-01", gpu_id="0", timestamp=None, **kwargs):
    ts = timestamp or time.time()
    base = {
        "DCGM_FI_DEV_GPU_UTIL": 75.0,
        "DCGM_FI_DEV_GPU_TEMP": 65.0,
        "DCGM_FI_DEV_FB_USED": 40960.0,
        "DCGM_FI_DEV_FB_FREE": 40960.0,
    }
    base.update(kwargs)
    return [
        GpuMetric(
            timestamp=ts,
            host=host,
            gpu_id=gpu_id,
            metric_name=name,
            value=val,
            labels={},
        )
        for name, val in base.items()
    ]


class TestMetricStorage:
    def test_store_and_retrieve(self, storage):
        metrics = make_metrics()
        count = storage.store_metrics(metrics)
        assert count == len(metrics)

        latest = storage.get_latest()
        assert len(latest) == len(metrics)

    def test_get_latest_returns_newest(self, storage):
        old_ts = time.time() - 10
        new_ts = time.time()

        storage.store_metrics(make_metrics(timestamp=old_ts, DCGM_FI_DEV_GPU_UTIL=50.0))
        storage.store_metrics(make_metrics(timestamp=new_ts, DCGM_FI_DEV_GPU_UTIL=90.0))

        latest = storage.get_latest()
        util_row = next(r for r in latest if r["metric_name"] == "DCGM_FI_DEV_GPU_UTIL")
        assert util_row["value"] == 90.0

    def test_get_recent(self, storage):
        old_ts = time.time() - 600  # 10분 전
        new_ts = time.time()

        storage.store_metrics(make_metrics(timestamp=old_ts))
        storage.store_metrics(make_metrics(timestamp=new_ts))

        recent = storage.get_recent(minutes=5)
        # 최근 5분 → old_ts는 제외
        assert all(r["timestamp"] >= new_ts - 300 for r in recent)

    def test_get_range(self, storage):
        ts1 = 1000.0
        ts2 = 2000.0
        ts3 = 3000.0

        storage.store_metrics(make_metrics(timestamp=ts1))
        storage.store_metrics(make_metrics(timestamp=ts2))
        storage.store_metrics(make_metrics(timestamp=ts3))

        result = storage.get_range(1500, 2500)
        assert all(r["timestamp"] == ts2 for r in result)

    def test_get_range_with_filters(self, storage):
        ts = time.time()
        storage.store_metrics(make_metrics(host="vm-01", gpu_id="0", timestamp=ts))
        storage.store_metrics(make_metrics(host="vm-02", gpu_id="1", timestamp=ts))

        result = storage.get_range(ts - 1, ts + 1, host="vm-01")
        assert all(r["host"] == "vm-01" for r in result)

    def test_cleanup(self, storage):
        old_ts = time.time() - 200000  # 2+ days
        new_ts = time.time()

        storage.store_metrics(make_metrics(timestamp=old_ts))
        storage.store_metrics(make_metrics(timestamp=new_ts))

        deleted = storage.cleanup()
        assert deleted > 0

        remaining = storage.get_latest()
        assert all(r["timestamp"] == new_ts for r in remaining)

    def test_empty_store(self, storage):
        count = storage.store_metrics([])
        assert count == 0

    def test_multiple_hosts_gpus(self, storage):
        ts = time.time()
        all_metrics = []
        for host in ["vm-01", "vm-02"]:
            for gpu_id in ["0", "1"]:
                all_metrics.extend(make_metrics(host=host, gpu_id=gpu_id, timestamp=ts))

        storage.store_metrics(all_metrics)
        latest = storage.get_latest()

        hosts = {r["host"] for r in latest}
        assert hosts == {"vm-01", "vm-02"}
        gpu_ids = {r["gpu_id"] for r in latest}
        assert gpu_ids == {"0", "1"}
