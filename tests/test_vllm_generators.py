"""vLLM generators 테스트."""

import json
from pathlib import Path

import yaml
import pytest

from gpu_monitor.config import (
    AppConfig, VMConfig, VLLMConfig, VLLMModelConfig,
    PrometheusConfig, GrafanaConfig, load_config,
)
from gpu_monitor.generators.vllm_prometheus import generate_vllm_prometheus_config
from gpu_monitor.generators.vllm_grafana import generate_vllm_grafana_dashboard


@pytest.fixture
def vllm_config(tmp_path):
    return AppConfig(
        vms=[VMConfig(host="gpu-vm-01", port=9400)],
        prometheus=PrometheusConfig(output_dir=str(tmp_path / "prometheus")),
        grafana=GrafanaConfig(
            output_dir=str(tmp_path / "grafana"),
            provisioning_dir=str(tmp_path / "grafana" / "provisioning"),
        ),
        vllm=VLLMConfig(
            scrape_interval="1s",
            job_name="vllm",
            models=[
                VLLMModelConfig(host="gpu-vm-01", port=8000, model_name="qwen3-30b"),
                VLLMModelConfig(host="gpu-vm-01", port=8001, model_name="llama-70b", gpu_vm="gpu-vm-01"),
                VLLMModelConfig(host="gpu-vm-02", port=8000, model_name="qwen3-30b-2"),
            ],
        ),
    )


# ---------- vLLM Prometheus ----------

class TestVLLMPrometheusGenerator:
    def test_generates_file(self, vllm_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_vllm_prometheus_config(vllm_config, output_dir=out)
        assert path.exists()
        assert path.name == "vllm_prometheus.yml"

    def test_contains_targets(self, vllm_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_vllm_prometheus_config(vllm_config, output_dir=out)
        data = yaml.safe_load(path.read_text())

        sc = data["scrape_configs"][0]
        all_targets = []
        for s in sc["static_configs"]:
            all_targets.extend(s["targets"])

        assert "gpu-vm-01:8000" in all_targets
        assert "gpu-vm-01:8001" in all_targets
        assert "gpu-vm-02:8000" in all_targets

    def test_model_name_labels(self, vllm_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_vllm_prometheus_config(vllm_config, output_dir=out)
        data = yaml.safe_load(path.read_text())

        sc = data["scrape_configs"][0]
        model_names = [s["labels"]["model_name"] for s in sc["static_configs"]]
        assert "qwen3-30b" in model_names
        assert "llama-70b" in model_names
        assert "qwen3-30b-2" in model_names

    def test_gpu_vm_label(self, vllm_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_vllm_prometheus_config(vllm_config, output_dir=out)
        data = yaml.safe_load(path.read_text())

        sc = data["scrape_configs"][0]
        # llama-70b has gpu_vm set
        llama_entry = [s for s in sc["static_configs"] if s["labels"]["model_name"] == "llama-70b"][0]
        assert llama_entry["labels"]["gpu_vm"] == "gpu-vm-01"

        # qwen3-30b has no gpu_vm
        qwen_entry = [s for s in sc["static_configs"] if s["labels"]["model_name"] == "qwen3-30b"][0]
        assert "gpu_vm" not in qwen_entry["labels"]

    def test_job_name(self, vllm_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_vllm_prometheus_config(vllm_config, output_dir=out)
        data = yaml.safe_load(path.read_text())
        assert data["scrape_configs"][0]["job_name"] == "vllm"

    def test_scrape_interval(self, vllm_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_vllm_prometheus_config(vllm_config, output_dir=out)
        data = yaml.safe_load(path.read_text())
        assert data["scrape_configs"][0]["scrape_interval"] == "1s"

    def test_relabel_instance(self, vllm_config, tmp_path):
        out = tmp_path / "prom"
        path = generate_vllm_prometheus_config(vllm_config, output_dir=out)
        data = yaml.safe_load(path.read_text())
        relabels = data["scrape_configs"][0]["relabel_configs"]
        assert len(relabels) >= 1
        assert relabels[0]["target_label"] == "instance"

    def test_empty_models(self, tmp_path):
        config = AppConfig(
            vllm=VLLMConfig(models=[]),
            prometheus=PrometheusConfig(output_dir=str(tmp_path)),
        )
        path = generate_vllm_prometheus_config(config, output_dir=tmp_path / "prom")
        data = yaml.safe_load(path.read_text())
        assert data["scrape_configs"][0]["static_configs"] == []


# ---------- vLLM Grafana ----------

class TestVLLMGrafanaGenerator:
    def test_generates_file(self, vllm_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_vllm_grafana_dashboard(vllm_config, output_dir=out)
        assert "dashboard_json" in paths
        assert paths["dashboard_json"].exists()
        assert paths["dashboard_json"].name == "vllm-monitor.json"

    def test_dashboard_metadata(self, vllm_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_vllm_grafana_dashboard(vllm_config, output_dir=out)
        dashboard = json.loads(paths["dashboard_json"].read_text())

        assert dashboard["uid"] == "vllm-monitor"
        assert dashboard["title"] == "vLLM Inference Monitor"
        assert "vllm" in dashboard["tags"]
        assert dashboard["refresh"] == "5s"

    def test_templating_variables(self, vllm_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_vllm_grafana_dashboard(vllm_config, output_dir=out)
        dashboard = json.loads(paths["dashboard_json"].read_text())

        var_names = [v["name"] for v in dashboard["templating"]["list"]]
        assert "model" in var_names
        assert "instance" in var_names
        assert "DS_PROMETHEUS" in var_names

    def test_panel_count(self, vllm_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_vllm_grafana_dashboard(vllm_config, output_dir=out)
        dashboard = json.loads(paths["dashboard_json"].read_text())

        panels = dashboard["panels"]
        # 5 rows + 5(overview) + 3(latency) + 4(queue) + 3(token) + 3(cache) = 23
        assert len(panels) >= 20

    def test_panel_types(self, vllm_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_vllm_grafana_dashboard(vllm_config, output_dir=out)
        dashboard = json.loads(paths["dashboard_json"].read_text())

        types = {p["type"] for p in dashboard["panels"]}
        assert "stat" in types
        assert "gauge" in types
        assert "timeseries" in types
        assert "row" in types

    def test_row_titles(self, vllm_config, tmp_path):
        out = tmp_path / "grafana"
        paths = generate_vllm_grafana_dashboard(vllm_config, output_dir=out)
        dashboard = json.loads(paths["dashboard_json"].read_text())

        row_titles = [p["title"] for p in dashboard["panels"] if p["type"] == "row"]
        assert "Overview" in row_titles
        assert "Latency" in row_titles
        assert "Queue & Processing" in row_titles
        assert "Token Distribution" in row_titles
        assert "Cache & Success" in row_titles

    def test_vllm_metrics_used(self, vllm_config, tmp_path):
        """핵심 vLLM 메트릭이 대시보드에 포함되어 있는지 확인."""
        out = tmp_path / "grafana"
        paths = generate_vllm_grafana_dashboard(vllm_config, output_dir=out)
        dashboard_text = paths["dashboard_json"].read_text()

        key_metrics = [
            "vllm:num_requests_running",
            "vllm:num_requests_waiting",
            "vllm:time_to_first_token_seconds_bucket",
            "vllm:e2e_request_latency_seconds_bucket",
            "vllm:gpu_cache_usage_perc",
            "vllm:prompt_tokens_total",
            "vllm:generation_tokens_total",
            "vllm:request_success_total",
        ]
        for metric in key_metrics:
            assert metric in dashboard_text, f"Missing metric: {metric}"

    def test_model_filter_in_queries(self, vllm_config, tmp_path):
        """패널 쿼리에 model_name 필터가 포함되어 있는지 확인."""
        out = tmp_path / "grafana"
        paths = generate_vllm_grafana_dashboard(vllm_config, output_dir=out)
        dashboard_text = paths["dashboard_json"].read_text()
        assert 'model_name=~\\"$model\\"' in dashboard_text


# ---------- config loading with vllm ----------

class TestConfigLoadingVLLM:
    def test_load_vllm_section(self, tmp_path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
vms:
  - host: "test-vm"
    port: 9400
vllm:
  scrape_interval: "2s"
  job_name: "vllm-test"
  models:
    - host: "gpu-vm-01"
      port: 8000
      model_name: "qwen3-30b"
    - host: "gpu-vm-02"
      port: 8001
      model_name: "llama-70b"
      gpu_vm: "gpu-vm-02"
""")
        config = load_config(config_yaml)

        assert config.vllm.scrape_interval == "2s"
        assert config.vllm.job_name == "vllm-test"
        assert len(config.vllm.models) == 2
        assert config.vllm.models[0].host == "gpu-vm-01"
        assert config.vllm.models[0].model_name == "qwen3-30b"
        assert config.vllm.models[1].gpu_vm == "gpu-vm-02"

    def test_load_without_vllm_section(self, tmp_path):
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("""
vms:
  - host: "test-vm"
    port: 9400
""")
        config = load_config(config_yaml)
        assert config.vllm.models == []
        assert config.vllm.scrape_interval == "1s"
        assert config.vllm.job_name == "vllm"

    def test_vllm_model_properties(self):
        m = VLLMModelConfig(host="gpu-vm-01", port=8000, model_name="qwen3")
        assert m.metrics_url == "http://gpu-vm-01:8000/metrics"
        assert m.target == "gpu-vm-01:8000"

    def test_vllm_defaults(self):
        config = AppConfig()
        assert isinstance(config.vllm, VLLMConfig)
        assert config.vllm.models == []
        assert config.vllm.scrape_interval == "1s"
