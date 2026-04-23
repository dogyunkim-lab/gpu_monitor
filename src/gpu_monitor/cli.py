"""Click 기반 CLI 엔트리포인트 — 설정 생성기 + 검증 유틸리티."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
import httpx

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
    """GPU Monitor — Prometheus + Grafana 설정 생성기"""
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config_path)
    ctx.obj["verbose"] = verbose


# ---------- generate ----------

@main.group()
def generate():
    """설정 파일 생성."""
    pass


@generate.command("prometheus")
@click.option("-o", "--output", default=None, help="출력 디렉토리")
@click.pass_context
def gen_prometheus(ctx, output):
    """prometheus.yml 생성."""
    from gpu_monitor.generators.prometheus import generate_prometheus_config

    config = ctx.obj["config"]
    out = Path(output) if output else None
    path = generate_prometheus_config(config, output_dir=out)
    click.echo(f"생성됨: {path}")


@generate.command("alerts")
@click.option("-o", "--output", default=None, help="출력 디렉토리")
@click.pass_context
def gen_alerts(ctx, output):
    """Prometheus alert rules 생성."""
    from gpu_monitor.generators.alerts import generate_alert_rules

    config = ctx.obj["config"]
    out = Path(output) if output else None
    path = generate_alert_rules(config, output_dir=out)
    click.echo(f"생성됨: {path}")


@generate.command("grafana")
@click.option("-o", "--output", default=None, help="출력 디렉토리")
@click.pass_context
def gen_grafana(ctx, output):
    """Grafana provisioning + dashboard JSON 생성."""
    from gpu_monitor.generators.grafana import generate_grafana_provisioning

    config = ctx.obj["config"]
    out = Path(output) if output else None
    paths = generate_grafana_provisioning(config, output_dir=out)
    for label, path in paths.items():
        click.echo(f"생성됨: {path}")


@generate.command("vllm-prometheus")
@click.option("-o", "--output", default=None, help="출력 디렉토리")
@click.pass_context
def gen_vllm_prometheus(ctx, output):
    """vLLM Prometheus scrape config 생성."""
    from gpu_monitor.generators.vllm_prometheus import generate_vllm_prometheus_config

    config = ctx.obj["config"]
    out = Path(output) if output else None
    path = generate_vllm_prometheus_config(config, output_dir=out)
    click.echo(f"생성됨: {path}")


@generate.command("vllm-grafana")
@click.option("-o", "--output", default=None, help="출력 디렉토리")
@click.pass_context
def gen_vllm_grafana(ctx, output):
    """vLLM Grafana 대시보드 JSON 생성."""
    from gpu_monitor.generators.vllm_grafana import generate_vllm_grafana_dashboard

    config = ctx.obj["config"]
    out = Path(output) if output else None
    paths = generate_vllm_grafana_dashboard(config, output_dir=out)
    for label, path in paths.items():
        click.echo(f"생성됨: {path}")


@generate.command("all")
@click.option("-o", "--output", default=None, help="출력 루트 디렉토리")
@click.pass_context
def gen_all(ctx, output):
    """prometheus.yml + alert rules + Grafana + vLLM 설정 모두 생성."""
    from gpu_monitor.generators.prometheus import generate_prometheus_config
    from gpu_monitor.generators.alerts import generate_alert_rules
    from gpu_monitor.generators.grafana import generate_grafana_provisioning
    from gpu_monitor.generators.vllm_grafana import generate_vllm_grafana_dashboard

    config = ctx.obj["config"]
    out = Path(output) if output else None

    prom_out = out / "prometheus" if out else None
    grafana_out = out / "grafana" if out else None

    p = generate_prometheus_config(config, output_dir=prom_out)
    click.echo(f"생성됨: {p}")

    a = generate_alert_rules(config, output_dir=prom_out)
    click.echo(f"생성됨: {a}")

    paths = generate_grafana_provisioning(config, output_dir=grafana_out)
    for label, path in paths.items():
        click.echo(f"생성됨: {path}")

    if config.vllm.models:
        vpaths = generate_vllm_grafana_dashboard(config, output_dir=grafana_out)
        for label, path in vpaths.items():
            click.echo(f"생성됨: {path}")

    click.echo("\n모든 설정 파일 생성 완료.")


# ---------- validate ----------

@main.command()
@click.pass_context
def validate(ctx):
    """config.yaml 검증 + DCGM exporter 연결 확인."""
    config = ctx.obj["config"]
    errors = []

    if not config.vms:
        errors.append("VM이 설정되지 않았습니다.")

    for vm in config.vms:
        if not vm.host:
            errors.append(f"VM '{vm.name}': host가 비어있습니다.")

    if errors:
        for e in errors:
            click.echo(f"  [ERROR] {e}", err=True)
        sys.exit(1)

    click.echo(f"설정 검증 통과: VM {len(config.vms)}대")

    # 연결 확인
    click.echo("\nDCGM exporter 연결 확인:")
    fail_count = 0
    for vm in config.vms:
        try:
            resp = httpx.get(vm.url, timeout=3.0)
            if resp.status_code == 200 and "DCGM_FI_DEV_GPU_UTIL" in resp.text:
                click.echo(f"  [OK]   {vm.name} ({vm.url})")
            else:
                click.echo(f"  [WARN] {vm.name} — HTTP {resp.status_code}, DCGM 메트릭 없음")
                fail_count += 1
        except httpx.RequestError as exc:
            click.echo(f"  [FAIL] {vm.name} — {exc}")
            fail_count += 1

    if fail_count:
        click.echo(f"\n{fail_count}대 연결 실패")
        sys.exit(1)
    else:
        click.echo(f"\n전체 {len(config.vms)}대 정상")


# ---------- status ----------

@main.command()
@click.pass_context
def status(ctx):
    """각 VM DCGM exporter 상태 확인."""
    config = ctx.obj["config"]

    if not config.vms:
        click.echo("설정된 VM이 없습니다.")
        return

    click.echo(f"{'VM':<20} {'Host:Port':<25} {'Status':<10} {'GPUs':<6}")
    click.echo("-" * 65)

    for vm in config.vms:
        try:
            resp = httpx.get(vm.url, timeout=3.0)
            if resp.status_code == 200:
                gpu_lines = [l for l in resp.text.splitlines()
                             if l.startswith("DCGM_FI_DEV_GPU_UTIL{")]
                gpu_count = len(gpu_lines)
                click.echo(f"{vm.name:<20} {vm.host}:{vm.port:<18} {'UP':<10} {gpu_count:<6}")
            else:
                click.echo(f"{vm.name:<20} {vm.host}:{vm.port:<18} {'HTTP ' + str(resp.status_code):<10} {'-':<6}")
        except httpx.RequestError:
            click.echo(f"{vm.name:<20} {vm.host}:{vm.port:<18} {'DOWN':<10} {'-':<6}")


# ---------- vllm-status ----------

@main.command("vllm-status")
@click.pass_context
def vllm_status(ctx):
    """각 vLLM 서버 /metrics 연결 확인."""
    config = ctx.obj["config"]

    if not config.vllm.models:
        click.echo("설정된 vLLM 모델이 없습니다.")
        return

    click.echo(f"{'Model':<25} {'Host:Port':<25} {'Status':<10}")
    click.echo("-" * 60)

    for m in config.vllm.models:
        try:
            resp = httpx.get(m.metrics_url, timeout=3.0)
            if resp.status_code == 200 and "vllm:" in resp.text:
                click.echo(f"{m.model_name:<25} {m.target:<25} {'UP':<10}")
            else:
                click.echo(f"{m.model_name:<25} {m.target:<25} {'HTTP ' + str(resp.status_code):<10}")
        except httpx.RequestError:
            click.echo(f"{m.model_name:<25} {m.target:<25} {'DOWN':<10}")


if __name__ == "__main__":
    main()
