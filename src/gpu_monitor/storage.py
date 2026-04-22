"""SQLite 기반 시계열 메트릭 저장소."""

from __future__ import annotations

import sqlite3
import time
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from gpu_monitor.parser import GpuMetric


class MetricStorage:
    """SQLite 기반 메트릭 저장/조회."""

    def __init__(self, db_path: str = "gpu_metrics.db", retention_days: int = 7):
        self.db_path = db_path
        self.retention_days = retention_days
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                host TEXT NOT NULL,
                gpu_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_metrics_ts
                ON metrics(timestamp);
            CREATE INDEX IF NOT EXISTS idx_metrics_host_gpu
                ON metrics(host, gpu_id, metric_name, timestamp);
        """)
        conn.commit()
        conn.close()

    def store_metrics(self, metrics: List[GpuMetric]) -> int:
        """메트릭 일괄 저장. 저장된 행 수 반환."""
        if not metrics:
            return 0
        rows = [
            (m.timestamp, m.host, m.gpu_id, m.metric_name, m.value)
            for m in metrics
        ]
        with self._cursor() as cur:
            cur.executemany(
                "INSERT INTO metrics (timestamp, host, gpu_id, metric_name, value) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def get_latest(self) -> List[Dict]:
        """각 (host, gpu_id, metric_name) 조합의 최신 값 조회."""
        with self._cursor() as cur:
            cur.execute("""
                SELECT m.timestamp, m.host, m.gpu_id, m.metric_name, m.value
                FROM metrics m
                INNER JOIN (
                    SELECT host, gpu_id, metric_name, MAX(timestamp) as max_ts
                    FROM metrics
                    GROUP BY host, gpu_id, metric_name
                ) latest ON m.host = latest.host
                    AND m.gpu_id = latest.gpu_id
                    AND m.metric_name = latest.metric_name
                    AND m.timestamp = latest.max_ts
            """)
            return [
                {
                    "timestamp": row[0],
                    "host": row[1],
                    "gpu_id": row[2],
                    "metric_name": row[3],
                    "value": row[4],
                }
                for row in cur.fetchall()
            ]

    def get_recent(self, minutes: int = 5) -> List[Dict]:
        """최근 N분간 메트릭 조회."""
        cutoff = time.time() - (minutes * 60)
        with self._cursor() as cur:
            cur.execute(
                "SELECT timestamp, host, gpu_id, metric_name, value "
                "FROM metrics WHERE timestamp >= ? ORDER BY timestamp",
                (cutoff,),
            )
            return [
                {
                    "timestamp": row[0],
                    "host": row[1],
                    "gpu_id": row[2],
                    "metric_name": row[3],
                    "value": row[4],
                }
                for row in cur.fetchall()
            ]

    def get_range(
        self,
        start_ts: float,
        end_ts: float,
        host: Optional[str] = None,
        gpu_id: Optional[str] = None,
        metric_name: Optional[str] = None,
    ) -> List[Dict]:
        """특정 시간 구간 메트릭 조회."""
        query = "SELECT timestamp, host, gpu_id, metric_name, value FROM metrics WHERE timestamp BETWEEN ? AND ?"
        params: list = [start_ts, end_ts]

        if host:
            query += " AND host = ?"
            params.append(host)
        if gpu_id is not None:
            query += " AND gpu_id = ?"
            params.append(gpu_id)
        if metric_name:
            query += " AND metric_name = ?"
            params.append(metric_name)

        query += " ORDER BY timestamp"

        with self._cursor() as cur:
            cur.execute(query, params)
            return [
                {
                    "timestamp": row[0],
                    "host": row[1],
                    "gpu_id": row[2],
                    "metric_name": row[3],
                    "value": row[4],
                }
                for row in cur.fetchall()
            ]

    def cleanup(self) -> int:
        """retention_days 이전 데이터 삭제. 삭제된 행 수 반환."""
        cutoff = time.time() - (self.retention_days * 86400)
        with self._cursor() as cur:
            cur.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
            return cur.rowcount

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
