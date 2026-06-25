"""Shared pytest fixtures.

The integration tests in ``test_inference.py`` hit the real Ollama stack and run
against a single, configurable vision model. Pick it with either (CLI wins):

    uv run pytest --model minicpm-v4.6:latest
    ARMA_WATCHER_TEST_MODEL=minicpm-v4.6:latest uv run pytest

Both fall back to ``inference.MODEL`` (the app default) when unset, so a bare
``uv run pytest`` still exercises the shipping model.
"""
import os

import pytest

from arma_watcher.inference import MODEL, Inference


def pytest_addoption(parser):
    parser.addoption(
        "--model",
        action="store",
        default=None,
        help="Ollama vision model tag for the integration tests "
        "(overrides $ARMA_WATCHER_TEST_MODEL; defaults to inference.MODEL).",
    )


@pytest.fixture(scope="session")
def model(request):
    """Model under test: --model > $ARMA_WATCHER_TEST_MODEL > inference.MODEL."""
    return (
        request.config.getoption("--model")
        or os.environ.get("ARMA_WATCHER_TEST_MODEL")
        or MODEL
    )


@pytest.fixture(scope="session")
def inference(model):
    """An Inference bound to the selected model — use in every Ollama integration test."""
    return Inference(model=model)
