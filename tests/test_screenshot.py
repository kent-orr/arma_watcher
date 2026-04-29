"""
Tests for src/screenshot.py.

Integration-style: these hit the real mss/Windows display stack.
There is no mocking — if the display is gone, the tests fail, which is correct.
"""
import io

import pytest
from PIL import Image

from src.screenshot import capture_monitor, capture_to_bytes, list_monitors


# ---------------------------------------------------------------------------
# list_monitors
# ---------------------------------------------------------------------------


class TestListMonitors:
    def test_returns_a_list(self):
        assert isinstance(list_monitors(), list)

    def test_has_at_least_two_entries(self):
        # mss always gives monitors[0] (virtual all-monitors canvas) + at least one physical
        assert len(list_monitors()) >= 2

    def test_each_entry_has_geometry_keys(self):
        for monitor in list_monitors():
            assert "width" in monitor
            assert "height" in monitor
            assert "left" in monitor
            assert "top" in monitor

    def test_all_dimensions_are_positive_integers(self):
        for monitor in list_monitors():
            assert isinstance(monitor["width"], int) and monitor["width"] > 0
            assert isinstance(monitor["height"], int) and monitor["height"] > 0

    def test_returns_fresh_list_each_call(self):
        # Mutating the return value must not affect the next call
        first = list_monitors()
        first.clear()
        assert len(list_monitors()) >= 2


# ---------------------------------------------------------------------------
# capture_monitor — happy path
# ---------------------------------------------------------------------------


class TestCaptureMonitorHappyPath:
    def test_all_monitors_canvas_returns_image(self):
        img = capture_monitor(0)
        assert isinstance(img, Image.Image)

    def test_primary_monitor_returns_image(self):
        img = capture_monitor(1)
        assert isinstance(img, Image.Image)

    def test_image_mode_is_rgb(self):
        assert capture_monitor(1).mode == "RGB"

    def test_image_dimensions_match_monitor_info(self):
        monitors = list_monitors()
        img = capture_monitor(1)
        assert img.width == monitors[1]["width"]
        assert img.height == monitors[1]["height"]

    def test_all_monitors_canvas_wider_than_single(self):
        # The virtual canvas (0) must be at least as wide as monitor 1
        canvas = capture_monitor(0)
        primary = capture_monitor(1)
        assert canvas.width >= primary.width

    def test_image_has_non_uniform_pixels(self):
        # A real desktop screenshot is never a solid colour
        img = capture_monitor(1)
        extrema = img.getextrema()  # ((r_min, r_max), (g_min, g_max), (b_min, b_max))
        channel_ranges = [hi - lo for lo, hi in extrema]
        assert any(r > 0 for r in channel_ranges), "Screenshot looks like a blank/solid image"

    def test_second_monitor_if_available(self):
        monitors = list_monitors()
        if len(monitors) < 3:
            pytest.skip("Only one physical monitor detected")
        img = capture_monitor(2)
        assert isinstance(img, Image.Image)
        assert img.width == monitors[2]["width"]
        assert img.height == monitors[2]["height"]


# ---------------------------------------------------------------------------
# capture_monitor — error handling
# ---------------------------------------------------------------------------


class TestCaptureMonitorErrors:
    def test_negative_index_raises_value_error(self):
        with pytest.raises(ValueError, match="out of range"):
            capture_monitor(-1)

    def test_index_equal_to_monitor_count_raises_value_error(self):
        with pytest.raises(ValueError, match="out of range"):
            capture_monitor(len(list_monitors()))

    def test_large_index_raises_value_error(self):
        with pytest.raises(ValueError, match="out of range"):
            capture_monitor(999)

    def test_error_message_includes_valid_range(self):
        monitors = list_monitors()
        with pytest.raises(ValueError) as exc_info:
            capture_monitor(len(monitors))
        msg = str(exc_info.value)
        assert str(len(monitors) - 1) in msg


# ---------------------------------------------------------------------------
# capture_to_bytes
# ---------------------------------------------------------------------------


class TestCaptureToBytes:
    def test_returns_bytes(self):
        assert isinstance(capture_to_bytes(1), bytes)

    def test_default_format_is_png(self):
        data = capture_to_bytes(1)
        img = Image.open(io.BytesIO(data))
        assert img.format == "PNG"

    def test_jpeg_format_roundtrip(self):
        data = capture_to_bytes(1, fmt="JPEG")
        img = Image.open(io.BytesIO(data))
        assert img.format == "JPEG"

    def test_output_is_not_empty(self):
        assert len(capture_to_bytes(1)) > 0

    def test_png_bytes_start_with_png_magic(self):
        data = capture_to_bytes(1)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_roundtrip_preserves_dimensions(self):
        monitors = list_monitors()
        data = capture_to_bytes(1)
        img = Image.open(io.BytesIO(data))
        assert img.width == monitors[1]["width"]
        assert img.height == monitors[1]["height"]

    def test_invalid_index_propagates_value_error(self):
        with pytest.raises(ValueError):
            capture_to_bytes(999)
