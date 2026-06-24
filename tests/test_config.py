"""Tests for arma_watcher/config.py — the hardcoded cloud Service URL."""
from arma_watcher import config


def test_service_url_defaults_to_hardcoded(monkeypatch):
    monkeypatch.delenv("ARMA_WATCHER_PROXY_URL", raising=False)
    assert config.service_url() == config.SERVICE_URL


def test_service_url_is_the_expected_deployment():
    assert config.SERVICE_URL == "https://seal-app-spckf.ondigitalocean.app/"


def test_service_url_env_override_for_dev(monkeypatch):
    monkeypatch.setenv("ARMA_WATCHER_PROXY_URL", "http://localhost:5000")
    assert config.service_url() == "http://localhost:5000"


def test_proxy_url_no_longer_a_config_field():
    # Users never enter it, so it must not be a saved/overridable config key.
    assert "proxy_url" not in config.DEFAULTS
    assert "proxy_url" not in config._ENV_OVERRIDES
