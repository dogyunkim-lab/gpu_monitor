"""Recording 모드 — 고해상도 메트릭 기록."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from gpu_monitor.config import AppConfig
from gpu_monitor.collector import MetricCollector
from gpu_monitor.parser import GpuMetric

logger = logging.getLogger(__name__)


@dataclass
class RecordingSession:
    session_id: str
    label: str
    start_time: float
    end_time: Optional[float] = None
    interval_ms: int = 100
    db_path: str = ""


class Recorder:
    """고해상도 메트릭 기록 관리."""

    def __init__(self, config: AppConfig, collector: MetricCollector):
        self.config = config
        self.collector = collector
        self._output_dir = Path(config.recorder.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._current_session: Optional[RecordingSession] = None
        self._recording_db: Optional[sqlite3.Connection] = None

    def start(self, label: str = "recording") -> RecordingSession:
        """기록 시작."""
        if self._running:
            raise RuntimeError("이미 기록 중입니다")

        session_id = f"{int(time.time())}_{label}"
        db_path = str(self._output_dir / f"{session_id}.db")

        # 기록용 별도 SQLite 파일 생성
        self._recording_db = sqlite3.connect(db_path, check_same_thread=False)
        self._recording_db.execute("PRAGMA journal_mode=WAL")
        self._recording_db.executescript("""
            CREATE TABLE IF NOT EXISTS session_info (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                host TEXT NOT NULL,
                gpu_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rec_ts ON metrics(timestamp);
        """)

        self._current_session = RecordingSession(
            session_id=session_id,
            label=label,
            start_time=time.time(),
            interval_ms=self.config.recorder.interval_ms,
            db_path=db_path,
        )

        # 세션 정보 저장
        self._recording_db.executemany(
            "INSERT INTO session_info (key, value) VALUES (?, ?)",
            [
                ("session_id", session_id),
                ("label", label),
                ("start_time", str(self._current_session.start_time)),
                ("interval_ms", str(self.config.recorder.interval_ms)),
            ],
        )
        self._recording_db.commit()

        self._running = True
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

        logger.info("기록 시작: %s (간격: %dms)", label, self.config.recorder.interval_ms)
        return self._current_session

    def stop(self) -> Optional[RecordingSession]:
        """기록 중지. 세션 정보 반환."""
        if not self._running:
            return None

        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        session = self._current_session
        if session:
            session.end_time = time.time()
            if self._recording_db:
                self._recording_db.execute(
                    "INSERT OR REPLACE INTO session_info (key, value) VALUES (?, ?)",
                    ("end_time", str(session.end_time)),
                )
                self._recording_db.commit()
                self._recording_db.close()
                self._recording_db = None

        self._current_session = None
        logger.info("기록 중지: %s", session.label if session else "없음")
        return session

    def _record_loop(self):
        interval = self.config.recorder.interval_ms / 1000.0
        while self._running:
            start = time.time()
            try:
                metrics = self.collector.collect_all()
                self._store_recording(metrics)
            except Exception:
                logger.exception("기록 수집 에러")

            elapsed = time.time() - start
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                end_time = time.time() + sleep_time
                while self._running and time.time() < end_time:
                    time.sleep(min(0.01, end_time - time.time()))

    def _store_recording(self, metrics: List[GpuMetric]):
        if not metrics or not self._recording_db:
            return
        rows = [
            (m.timestamp, m.host, m.gpu_id, m.metric_name, m.value)
            for m in metrics
        ]
        self._recording_db.executemany(
            "INSERT INTO metrics (timestamp, host, gpu_id, metric_name, value) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._recording_db.commit()

    def list_sessions(self) -> List[Dict]:
        """저장된 기록 세션 목록."""
        sessions = []
        for db_file in self._output_dir.glob("*.db"):
            try:
                conn = sqlite3.connect(str(db_file))
                cur = conn.execute("SELECT key, value FROM session_info")
                info = dict(cur.fetchall())
                conn.close()
                sessions.append({
                    "session_id": info.get("session_id", db_file.stem),
                    "label": info.get("label", ""),
                    "start_time": float(info.get("start_time", 0)),
                    "end_time": float(info.get("end_time", 0)) if info.get("end_time") else None,
                    "interval_ms": int(info.get("interval_ms", 100)),
                    "db_path": str(db_file),
                })
            except Exception:
                continue
        return sorted(sessions, key=lambda s: s["start_time"], reverse=True)

    @property
    def is_recording(self) -> bool:
        return self._running

    @property
    def current_session(self) -> Optional[RecordingSession]:
        return self._current_session
