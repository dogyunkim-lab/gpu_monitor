"""Click 기반 CLI 엔트리포인트."""

from __future__ import annotations

import logging
import sys
import time

import click

from gpu_monitor import __version__
from gpu_monitor.config import load_config


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@click.group()
@click.version_option(__version__, prog_name="gpu-monitor")
@click.option("-c", "--config", "config_path", default=None, help="설정 파일 경로 (기본: config.yaml)")
@click.option("-v", "--verbose", is_flag=True, help="상세 로그 출력")
@click.pass_context
def main(ctx, config_path, verbose):
    """GPU Monitor — DCGM exporter 기반 다중 GPU VM 통합 모니터링"""
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config_path)
    ctx.obj["verbose"] = verbose


@main.command()
@click.pass_context
def start(ctx):
    """수집 + 웹 대시보드 시작."""
    config = ctx.obj["config"]
    logger = logging.getLogger(__name__)

    if not config.vms:
        logger.warning("설정된 VM이 없습니다. config.yaml을 확인하세요.")

    from gpu_monitor.storage import MetricStorage
    from gpu_monitor.collector import MetricCollector
    from gpu_monitor.alerts import AlertManager
    from gpu_monitor.recorder import Recorder
    from gpu_monitor.web.server import init_app

    storage = MetricStorage(
        db_path=config.storage.db_path,
        retention_days=config.storage.retention_days,
    )
    alert_manager = AlertManager(config.alerts)
    collector = MetricCollector(
        config=config,
        storage=storage,
        on_metrics=alert_manager.process_metrics,
    )
    recorder = Recorder(config=config, collector=collector)

    # 수집 시작
    collector.start()

    # 웹 서버 시작
    app = init_app(storage, collector, alert_manager, recorder)
    logger.info("웹 대시보드: http://%s:%d", config.web.host, config.web.port)

    try:
        app.run(
            host=config.web.host,
            port=config.web.port,
            debug=False,
            use_reloader=False,
        )
    except KeyboardInterrupt:
        pass
    finally:
        collector.stop()
        storage.close()
        logger.info("GPU Monitor 종료")


@main.command()
@click.pass_context
def status(ctx):
    """현재 GPU 상태 확인 (CLI 출력)."""
    config = ctx.obj["config"]

    from gpu_monitor.storage import MetricStorage
    from gpu_monitor.collector import MetricCollector

    storage = MetricStorage(db_path=config.storage.db_path)
    collector = MetricCollector(config=config, storage=storage)

    click.echo(f"수집 대상 VM: {len(config.vms)}대")
    for vm in config.vms:
        click.echo(f"  - {vm.name} ({vm.url})")

    click.echo("\n현재 메트릭 수집 중...")
    metrics = collector.collect_all()

    if not metrics:
        click.echo("수집된 메트릭이 없습니다.")
        storage.close()
        return

    # (host, gpu_id) 그룹핑
    gpus = {}
    for m in metrics:
        key = (m.host, m.gpu_id)
        gpus.setdefault(key, {})[m.metric_name] = m.value

    click.echo(f"\n{'Host':<20} {'GPU':<6} {'Util%':<8} {'MemBW%':<8} {'Temp°C':<8} {'Power W':<8} {'VRAM MiB':<12}")
    click.echo("-" * 80)

    for (host, gpu_id), vals in sorted(gpus.items()):
        util = vals.get("DCGM_FI_DEV_GPU_UTIL", 0)
        mem_bw = vals.get("DCGM_FI_DEV_MEM_COPY_UTIL", 0)
        temp = vals.get("DCGM_FI_DEV_GPU_TEMP", 0)
        power = vals.get("DCGM_FI_DEV_POWER_USAGE", 0)
        vram_used = vals.get("DCGM_FI_DEV_FB_USED", 0)
        vram_free = vals.get("DCGM_FI_DEV_FB_FREE", 0)

        click.echo(
            f"{host:<20} {gpu_id:<6} {util:<8.1f} {mem_bw:<8.1f} {temp:<8.0f} {power:<8.1f} "
            f"{vram_used:.0f}/{vram_used + vram_free:.0f}"
        )

    storage.close()


@main.group()
def record():
    """기록 모드 (고해상도 데이터 수집)."""
    pass


@record.command("start")
@click.option("-l", "--label", default="recording", help="기록 라벨")
@click.pass_context
def record_start(ctx, label):
    """기록 시작."""
    config = ctx.obj["config"]

    from gpu_monitor.storage import MetricStorage
    from gpu_monitor.collector import MetricCollector
    from gpu_monitor.alerts import AlertManager
    from gpu_monitor.recorder import Recorder

    storage = MetricStorage(db_path=config.storage.db_path)
    alert_manager = AlertManager(config.alerts)
    collector = MetricCollector(config=config, storage=storage, on_metrics=alert_manager.process_metrics)
    recorder = Recorder(config=config, collector=collector)

    session = recorder.start(label=label)
    click.echo(f"기록 시작: {session.session_id}")
    click.echo(f"  라벨: {session.label}")
    click.echo(f"  간격: {session.interval_ms}ms")
    click.echo(f"  DB: {session.db_path}")
    click.echo("\nCtrl+C로 중지...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        session = recorder.stop()
        if session and session.end_time:
            duration = session.end_time - session.start_time
            click.echo(f"\n기록 종료 ({duration:.1f}초)")
            click.echo(f"  DB: {session.db_path}")
    finally:
        collector.stop()
        storage.close()


@record.command("list")
@click.pass_context
def record_list(ctx):
    """저장된 기록 세션 목록."""
    config = ctx.obj["config"]

    from gpu_monitor.storage import MetricStorage
    from gpu_monitor.collector import MetricCollector
    from gpu_monitor.recorder import Recorder

    storage = MetricStorage(db_path=config.storage.db_path)
    collector = MetricCollector(config=config, storage=storage)
    recorder = Recorder(config=config, collector=collector)

    sessions = recorder.list_sessions()
    if not sessions:
        click.echo("저장된 기록이 없습니다.")
        return

    for s in sessions:
        duration = ""
        if s["end_time"]:
            dur = s["end_time"] - s["start_time"]
            duration = f" ({dur:.1f}초)"
        click.echo(f"  {s['session_id']}  [{s['label']}]{duration}")
        click.echo(f"    DB: {s['db_path']}")

    storage.close()


@main.command()
@click.argument("db_path")
@click.option("-o", "--output", default="reports", help="출력 디렉토리")
@click.pass_context
def report(ctx, db_path, output):
    """기록 세션 리포트 생성."""
    from gpu_monitor.reporter import Reporter

    reporter = Reporter(output_dir=output)
    click.echo(f"리포트 생성 중: {db_path}")

    result = reporter.generate_report(db_path)

    click.echo("\n" + result["summary"])
    click.echo(f"\nCSV: {result['csv_path']}")
    for p in result.get("chart_paths", []):
        click.echo(f"Chart: {p}")


@main.command()
@click.pass_context
def cleanup(ctx):
    """오래된 메트릭 데이터 정리."""
    config = ctx.obj["config"]

    from gpu_monitor.storage import MetricStorage

    storage = MetricStorage(
        db_path=config.storage.db_path,
        retention_days=config.storage.retention_days,
    )
    deleted = storage.cleanup()
    click.echo(f"{deleted}개 오래된 레코드 삭제 (retention: {config.storage.retention_days}일)")
    storage.close()


if __name__ == "__main__":
    main()
