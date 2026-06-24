"""
Tests for the billing/settings UI behaviors in arma_watcher/gui.py:

  1. Subscribe is hidden once a license key is present (already a subscriber).
  2. "Tip the Developer" is always visible and uses a static Stripe Payment
     Link — no email or Service URL needed (so it works in local mode too).
  3. Queue/Detect interval spinboxes are hidden in cloud mode.
  4. Starting a subscription checkout logs the license-key-by-email note.

These flow tests need a Tk display and skip automatically when none exists.
Visibility is probed with winfo_manager() (== "" once pack_forget/grid_remove'd).
"""
import tkinter as tk

import pytest

from arma_watcher import gui

_MODE_LOCAL = gui._MODE_LOCAL
_MODE_CLOUD = gui._MODE_CLOUD


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


def _visible(w) -> bool:
    return bool(w.winfo_manager())


class TestTipButton:
    def test_label_is_tip_the_developer(self, app):
        assert app._donate_btn.cget("text") == "Tip the Developer"

    def test_visible_in_local_mode(self, app):
        app._sv["inference_mode"].set(_MODE_LOCAL)
        assert _visible(app._donate_btn)

    def test_visible_in_cloud_mode(self, app):
        app._sv["inference_mode"].set(_MODE_CLOUD)
        assert _visible(app._donate_btn)

    def test_opens_payment_link_without_email_or_proxy(self, app, monkeypatch):
        opened = []
        monkeypatch.setattr(gui.webbrowser, "open", lambda u: opened.append(u))
        monkeypatch.delenv(gui.TIP_PAYMENT_LINK_ENV, raising=False)
        # Local mode: no Service URL, no Subscription Email set.
        app._sv["inference_mode"].set(_MODE_LOCAL)
        app._open_tip()
        assert opened == [gui.TIP_PAYMENT_LINK]

    def test_env_var_overrides_payment_link(self, app, monkeypatch):
        opened = []
        monkeypatch.setattr(gui.webbrowser, "open", lambda u: opened.append(u))
        monkeypatch.setenv(gui.TIP_PAYMENT_LINK_ENV, "https://buy.stripe.com/test_abc")
        app._open_tip()
        assert opened == ["https://buy.stripe.com/test_abc"]


class TestSubscribeVisibility:
    def test_hidden_in_local_mode(self, app):
        app._sv["inference_mode"].set(_MODE_LOCAL)
        assert not _visible(app._subscribe_btn)

    def test_visible_in_cloud_without_key(self, app):
        app._sv["inference_mode"].set(_MODE_CLOUD)
        app._sv["license_key"].set("")
        assert _visible(app._subscribe_btn)

    def test_hidden_in_cloud_with_key(self, app):
        app._sv["inference_mode"].set(_MODE_CLOUD)
        app._sv["license_key"].set("lk_abc123")
        assert not _visible(app._subscribe_btn)

    def test_reappears_when_key_cleared(self, app):
        app._sv["inference_mode"].set(_MODE_CLOUD)
        app._sv["license_key"].set("lk_abc123")
        assert not _visible(app._subscribe_btn)
        app._sv["license_key"].set("   ")  # whitespace counts as empty
        assert _visible(app._subscribe_btn)


class TestIntervalVisibility:
    def test_intervals_hidden_in_cloud(self, app):
        app._sv["inference_mode"].set(_MODE_CLOUD)
        for key in ("interval", "detect_interval"):
            _lbl, w = app._field_widgets[key]
            assert not _visible(w), f"{key} should be hidden in cloud mode"

    def test_intervals_visible_in_local(self, app):
        app._sv["inference_mode"].set(_MODE_LOCAL)
        for key in ("interval", "detect_interval"):
            _lbl, w = app._field_widgets[key]
            assert _visible(w), f"{key} should be visible in local mode"


class TestCheckoutMessage:
    def test_subscribe_checkout_logs_license_email_note(self, app, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            app, "_open_billing",
            lambda path, body, success_msg, no_sub_msg: captured.update(
                path=path, body=body, success=success_msg
            ),
        )
        app._sv["subscription_email"].set("user@example.com")
        app._open_checkout("sub")
        assert captured["path"] == "/checkout"
        assert captured["body"]["kind"] == "sub"
        msg = captured["success"].lower()
        assert "email" in msg
        assert "license key" in msg
