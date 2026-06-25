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


# ── Model selection ──────────────────────────────────────────────────────────
# The recommended list is curated (4b + 9b), but users may run ANY Ollama model:
# setup accepts a typed name and the GUI's Model field is a free-text combo.

def test_recommended_models_are_4b_and_9b():
    assert config.RECOMMENDED_MODELS == ["qwen3.5:4b", "qwen3.5:9b"]


def test_recommended_models_match_the_curated_table():
    # RECOMMENDED_MODELS must stay derived from _MODELS — one source of truth.
    assert config.RECOMMENDED_MODELS == [name for name, _vram in config._MODELS]


def test_pick_model_empty_input_returns_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert config._pick_model() == "qwen3.5:9b"


def test_pick_model_by_number(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "1")
    assert config._pick_model() == "qwen3.5:4b"


def test_pick_model_accepts_any_custom_model_name(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "minicpm-v4.6:latest")
    assert config._pick_model() == "minicpm-v4.6:latest"


def test_pick_model_reprompts_on_out_of_range_number(monkeypatch):
    answers = iter(["99", "2"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert config._pick_model() == "qwen3.5:9b"
