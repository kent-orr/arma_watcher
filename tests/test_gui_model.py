"""
The Model field is a free-text combo: users can type ANY Ollama model name,
with the recommended models (config.RECOMMENDED_MODELS) offered as dropdown
suggestions. These flow tests need a Tk display and skip when none exists.
"""
import tkinter as tk

import pytest

from arma_watcher import config, gui


@pytest.fixture
def app():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    root.withdraw()
    g = gui.WatcherGUI(root)
    try:
        yield g
    finally:
        root.destroy()


def test_gui_suggestions_come_from_config():
    # No duplicated list — the GUI reuses the curated recommended models.
    assert gui._MODELS == config.RECOMMENDED_MODELS


def test_model_field_is_editable(app):
    # A readonly combo would block typing a custom model name.
    _lbl, w = app._field_widgets["model"]
    assert str(w.cget("state")) != "readonly"


def test_model_field_offers_recommended_suggestions(app):
    _lbl, w = app._field_widgets["model"]
    values = [str(v) for v in w.cget("values")]
    assert values == config.RECOMMENDED_MODELS


def test_typed_custom_model_is_persisted(app, monkeypatch):
    # A model that isn't one of the suggestions must survive the save path.
    # Stub load/save so the test never touches the real config.json.
    monkeypatch.setattr(config, "load", lambda: dict(config.DEFAULTS))
    written = {}
    monkeypatch.setattr(config, "save", lambda cfg: written.update(cfg))

    app._sv["model"].set("minicpm-v4.6:latest")
    cfg = app._persist_settings()

    assert cfg["model"] == "minicpm-v4.6:latest"
    assert written["model"] == "minicpm-v4.6:latest"
