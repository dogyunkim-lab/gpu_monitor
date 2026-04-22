"""Report 생성 — 기록 세션 분석, 통계, 그래프, CSV 내보내기."""

from __future__ import annotations

import csv
import io
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


class Reporter:
    """기록 세션 분석 및 리포트 생성."""

    def __init__(self, output_dir: str = "reports"):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def load_session(self, db_path: str) -> pd.DataFrame:
        """기록 DB에서 DataFrame 로드."""
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(
            "SELECT timestamp, host, gpu_id, metric_name, value FROM metrics ORDER BY timestamp",
            conn,
        )
        conn.close()
        return df

    def compute_stats(self, df: pd.DataFrame) -> pd.DataFrame:
        """호스트/GPU/메트릭별 통계 계산 (평균, P50, P95, P99, Max, Min)."""
        if df.empty:
            return pd.DataFrame()

        stats = df.groupby(["host", "gpu_id", "metric_name"])["value"].agg(
            mean="mean",
            p50=lambda x: x.quantile(0.5),
            p95=lambda x: x.quantile(0.95),
            p99=lambda x: x.quantile(0.99),
            max="max",
            min="min",
            count="count",
        ).reset_index()

        return stats

    def generate_charts(self, df: pd.DataFrame, session_label: str) -> List[str]:
        """matplotlib 시계열 그래프 PNG 생성. 생성된 파일 경로 리스트 반환."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from datetime import datetime

        if df.empty:
            return []

        chart_paths = []
        key_metrics = [
            "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE",
            "DCGM_FI_PROF_DRAM_ACTIVE",
            "DCGM_FI_DEV_GPU_UTIL",
            "DCGM_FI_DEV_MEM_COPY_UTIL",
            "DCGM_FI_DEV_GPU_TEMP",
            "DCGM_FI_DEV_POWER_USAGE",
        ]

        for metric_name in key_metrics:
            mdf = df[df["metric_name"] == metric_name]
            if mdf.empty:
                continue

            fig, ax = plt.subplots(figsize=(14, 6))
            for (host, gpu_id), gdf in mdf.groupby(["host", "gpu_id"]):
                timestamps = [datetime.fromtimestamp(t) for t in gdf["timestamp"]]
                ax.plot(timestamps, gdf["value"], label=f"{host} GPU {gpu_id}", linewidth=0.8)

            ax.set_title(f"{metric_name}\n{session_label}", fontsize=12)
            ax.set_xlabel("Time")
            ax.set_ylabel("Value")
            ax.legend(fontsize=8, loc="upper right")
            ax.grid(True, alpha=0.3)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            fig.autofmt_xdate()
            plt.tight_layout()

            filename = f"{session_label}_{metric_name}.png"
            filepath = self._output_dir / filename
            fig.savefig(filepath, dpi=150)
            plt.close(fig)
            chart_paths.append(str(filepath))

        return chart_paths

    def export_csv(self, df: pd.DataFrame, session_label: str) -> str:
        """DataFrame을 CSV로 내보내기."""
        filepath = self._output_dir / f"{session_label}_data.csv"
        df.to_csv(filepath, index=False)
        return str(filepath)

    def generate_summary(
        self,
        stats: pd.DataFrame,
        session_label: str,
        duration_seconds: float,
    ) -> str:
        """텍스트 요약 리포트 생성."""
        lines = [
            f"{'=' * 60}",
            f"  GPU Monitor Report — {session_label}",
            f"{'=' * 60}",
            f"  기록 시간: {duration_seconds:.1f}초",
            f"  데이터 포인트: {stats['count'].sum():.0f}",
            "",
        ]

        if not stats.empty:
            for metric_name, mdf in stats.groupby("metric_name"):
                lines.append(f"--- {metric_name} ---")
                for _, row in mdf.iterrows():
                    lines.append(
                        f"  {row['host']} GPU {row['gpu_id']}: "
                        f"avg={row['mean']:.2f}  p50={row['p50']:.2f}  "
                        f"p95={row['p95']:.2f}  p99={row['p99']:.2f}  "
                        f"max={row['max']:.2f}"
                    )
                lines.append("")

        lines.append(f"{'=' * 60}")
        report_text = "\n".join(lines)

        filepath = self._output_dir / f"{session_label}_report.txt"
        filepath.write_text(report_text, encoding="utf-8")

        return report_text

    def generate_report(self, db_path: str) -> Dict[str, str]:
        """전체 리포트 생성 (통계 + 그래프 + CSV + 요약)."""
        # 세션 정보 로드
        conn = sqlite3.connect(db_path)
        try:
            info = dict(conn.execute("SELECT key, value FROM session_info").fetchall())
        except Exception:
            info = {}
        conn.close()

        label = info.get("label", Path(db_path).stem)
        start_time = float(info.get("start_time", 0))
        end_time = float(info.get("end_time", time.time()))
        duration = end_time - start_time

        df = self.load_session(db_path)
        stats = self.compute_stats(df)

        chart_paths = self.generate_charts(df, label)
        csv_path = self.export_csv(df, label)
        summary = self.generate_summary(stats, label, duration)

        return {
            "summary": summary,
            "csv_path": csv_path,
            "chart_paths": chart_paths,
            "stats": stats.to_dict("records") if not stats.empty else [],
        }
