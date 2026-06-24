"""
Tests for the Terms of Service / Privacy consent gate in arma_watcher/gui.py.

The legal-text tests are pure (no display). The flow tests build a real Tk root
and are skipped automatically when no display is available.
"""
import tkinter as tk

import pytest

from arma_watcher import gui


# ---------------------------------------------------------------------------
# Legal text content (pure — no display needed)
# ---------------------------------------------------------------------------


class TestLegalText:
    def test_terms_cover_image_abuse_and_do_terms(self):
        t = gui.TERMS_TEXT.lower()
        assert "abuse" in t
        assert "digitalocean" in t
        assert "acceptable use" in t

    def test_terms_limit_liability_to_amount_paid(self):
        t = gui.TERMS_TEXT.lower()
        assert "liability" in t
        assert "amount you have actually paid" in t

    def test_terms_disclaim_warranty(self):
        assert '"as is"' in gui.TERMS_TEXT

    def test_privacy_states_we_cannot_view_images(self):
        p = gui.PRIVACY_TEXT.lower()
        assert "cannot view your images" in p
        assert "no mechanism to view" in p

    def test_privacy_states_images_never_stored(self):
        p = gui.PRIVACY_TEXT.lower()
        assert "never written to disk" in p

    def test_privacy_warns_screenshots_leave_the_machine(self):
        p = gui.PRIVACY_TEXT.lower()
        assert "off of your computer" in p

    def test_privacy_names_stripe_and_digitalocean(self):
        p = gui.PRIVACY_TEXT.lower()
        assert "stripe" in p
        assert "digitalocean" in p

    def test_link_urls_point_at_real_policies(self):
        assert gui.LEGAL_STRIPE_PRIVACY.startswith("https://stripe.com/")
        assert "digitalocean.com" in gui.LEGAL_DO_AUP
        assert "digitalocean.com" in gui.LEGAL_DO_PRIVACY


# ---------------------------------------------------------------------------
# Consent flow (requires a Tk display)
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    root.withdraw()
    g = gui.WatcherGUI(root)
    # Record checkout calls instead of hitting the network.
    g._checkout_calls = []
    g._open_checkout = lambda kind: g._checkout_calls.append(kind)
    try:
        yield g
    finally:
        root.destroy()


class TestConsentFlow:
    def test_subscribe_does_not_checkout_immediately(self, app):
        app._subscribe()
        assert app._checkout_calls == []
        assert app._legal_dialog.winfo_exists()

    def test_agree_button_disabled_until_box_checked(self, app):
        app._subscribe()
        assert str(app._legal_agree_btn["state"]) == "disabled"
        app._legal_agree_var.set(True)
        app._sync_legal_agree_state()
        assert str(app._legal_agree_btn["state"]) == "normal"

    def test_accepting_proceeds_to_checkout(self, app):
        app._subscribe()
        app._legal_agree_var.set(True)
        app._sync_legal_agree_state()
        app._legal_accept()
        assert app._checkout_calls == ["sub"]

    def test_cancelling_does_not_checkout(self, app):
        app._subscribe()
        dlg = app._legal_dialog
        app._legal_cancel()
        assert app._checkout_calls == []
        assert not dlg.winfo_exists()
