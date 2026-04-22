"""generators 패키지 테스트."""

import json
from pathlib import Path

import yaml
import pytest

from gpu_monitor.config import AppConfig, VMConfig, AlertConfig, PrometheusConfig, GrafanaConfig
from gpu_monitor.generators.prometheus import generate_prometheus_config
from gpu_monitor.generators.alerts import generate_alert_rules
from gpu_monitor.generators.grafana import generate_grafana_provisioning


# ---------- prometheus.yml ----------

class TestPrometheusGenerator:
    def test_generates_file(self, sample_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_prometheus_config(sample_config, output_dir=out)
        assert path.exists()
        assert path.name == "prometheus.yml"

    def test_contains_targets(self, sample_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_prometheus_config(sample_config, output_dir=out)
        data = yaml.safe_load(path.read_text())

        targets = data["scrape_configs"][0]["static_configs"][0]["targets"]
        assert "gpu-vm-01:9400" in targets
        assert "gpu-vm-02:9400" in targets

    def test_scrape_interval(self, sample_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_prometheus_config(sample_config, output_dir=out)
        data = yaml.safe_load(path.read_text())
        assert data["global"]["scrape_interval"] == "5s"

    def test_job_name(self, sample_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_prometheus_config(sample_config, output_dir=out)
        data = yaml.safe_load(path.read_text())
        assert data["scrape_configs"][0]["job_name"] == "dcgm"

    def test_relabel_config(self, sample_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_prometheus_config(sample_config, output_dir=out)
        data = yaml.safe_load(path.read_text())
        relabels = data["scrape_configs"][0]["relabel_configs"]
        assert len(relabels) >= 1
        assert relabels[0]["target_label"] == "vm"

    def test_empty_vms(self, tmp_path):
        config = AppConfig(vms=[], prometheus=PrometheusConfig(output_dir=str(tmp_path / "prom")))
        path = generate_prometheus_config(config, output_dir=tmp_path / "prom")
        data = yaml.safe_load(path.read_text())
        targets = data["scrape_configs"][0]["static_configs"][0]["targets"]
        assert targets == []


# ---------- alert rules ----------

class TestAlertsGenerator:
    def test_generates_file(self, sample_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_alert_rules(sample_config, output_dir=out)
        assert path.exists()
        assert path.name == "gpu_alerts.yml"

    def test_contains_rules(self, sample_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_alert_rules(sample_config, output_dir=out)
        data = yaml.safe_load(path.read_text())

        rules = data["groups"][0]["rules"]
        alert_names = [r["alert"] for r in rules]
        assert "HighGPUUtilization" in alert_names
        assert "HighGPUTemperature" in alert_names
        assert "HighVRAMUtilization" in alert_names
        assert "HighPowerUsage" in alert_names
        assert "DCGMExporterDown" in alert_names

    def test_threshold_values(self, sample_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_alert_rules(sample_config, output_dir=out)
        data = yaml.safe_load(path.read_text())

        rules = {r["alert"]: r for r in data["groups"][0]["rules"]}
        assert "90.0" in rules["HighGPUUtilization"]["expr"]
        assert "80.0" in rules["HighGPUTemperature"]["expr"]

    def test_duration(self, sample_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_alert_rules(sample_config, output_dir=out)
        data = yaml.safe_load(path.read_text())

        rules = {r["alert"]: r for r in data["groups"][0]["rules"]}
        assert rules["HighGPUUtilization"]["for"] == "1m"

    def test_severity_labels(self, sample_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_alert_rules(sample_config, output_dir=out)
        data = yaml.safe_load(path.read_text())

        rules = {r["alert"]: r for r in data["groups"][0]["rules"]}
        assert rules["HighGPUTemperature"]["labels"]["severity"] == "critical"
        assert rules["DCGMExporterDown"]["labels"]["severity"] == "critical"
        assert rules["HighGPUUtilization"]["labels"]["severity"] == "warning"


# ---------- Grafana ----------

class TestGrafanaGenerator:
    def test_generates_files(self, sample_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_grafana_provisioning(sample_config, output_dir=out)
        assert "datasource" in paths
        assert "dashboard_provisioning" in paths
        assert "dashboard_json" in paths

        for p in paths.values():
            assert p.exists()

    def test_datasource_content(self, sample_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_grafana_provisioning(sample_config, output_dir=out)
        data = yaml.safe_load(paths["datasource"].read_text())
        ds = data["datasources"][0]
        assert ds["type"] == "prometheus"
        assert ds["url"] == "http://localhost:9090"
        assert ds["isDefault"] is True

    def test_dashboard_provisioning(self, sample_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_grafana_provisioning(sample_config, output_dir=out)
        data = yaml.safe_load(paths["dashboard_provisioning"].read_text())
        assert data["providers"][0]["type"] == "file"

    def test_dashboard_json_panels(self, sample_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_grafana_provisioning(sample_config, output_dir=out)
        dashboard = json.loads(paths["dashboard_json"].read_text())

        assert dashboard["title"] == "GPU Cluster Monitor"
        assert dashboard["uid"] == "gpu-cluster-monitor"

        panels = dashboard["panels"]
        # 15+ panels (including row panels)
        assert len(panels) >= 15

        # Check for expected panel types
        types = {p["type"] for p in panels}
        assert "stat" in types
        assert "gauge" in types
        assert "timeseries" in types
        assert "table" in types

    def test_dashboard_templating(self, sample_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_grafana_provisioning(sample_config, output_dir=out)
        dashboard = json.loads(paths["dashboard_json"].read_text())

        var_names = [v["name"] for v in dashboard["templating"]["list"]]
        assert "hostname" in var_names
        assert "gpu" in var_names

    def test_dashboard_refresh(self, sample_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_grafana_provisioning(sample_config, output_dir=out)
        dashboard = json.loads(paths["dashboard_json"].read_text())
        assert dashboard["refresh"] == "5s"


# ---------- config loading ----------

class TestConfigLoading:
    def test_load_with_new_fields(self, tmp_path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
vms:
  - host: "test-vm"
    port: 9400
alerts:
  gpu_util_threshold: 80.0
  temperature_threshold: 75.0
prometheus:
  scrape_interval: "10s"
grafana:
  datasource_url: "http://prom:9090"
""")
        from gpu_monitor.config import load_config
        config = load_config(config_yaml)

        assert len(config.vms) == 1
        assert config.vms[0].host == "test-vm"
        assert config.alerts.gpu_util_threshold == 80.0
        assert config.prometheus.scrape_interval == "10s"
        assert config.grafana.datasource_url == "http://prom:9090"

    def test_defaults(self):
        config = AppConfig()
        assert config.prometheus.scrape_interval == "5s"
        assert config.grafana.datasource_url == "http://localhost:9090"
        assert config.alerts.gpu_util_duration == "1m"
