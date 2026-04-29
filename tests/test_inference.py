"""
Tests for src/inference.py.

Init tests are pure unit tests (no ollama required).
Run tests hit the real ollama stack — ollama must be running with gemma4:e4b loaded.
"""
import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from arma_watcher.inference import MODEL, QUEUE_PROMPT, Inference, QueueInfo, ScreenState

QUEUE_TEST_IMAGE = Path(__file__).parent / "queue_test.png"


def _make_queue_image(position: int, server_name: str) -> bytes:
    """White 600x350 image with prominent server name and large centred position number."""
    img = Image.new("RGB", (600, 350), color="white")
    draw = ImageDraw.Draw(img)

    label_font = ImageFont.load_default(size=32)
    name_font = ImageFont.load_default(size=48)
    draw.text((20, 20), "Server Name:", fill="black", font=label_font)
    draw.text((20, 60), server_name, fill="black", font=name_font)

    label_font2 = ImageFont.load_default(size=32)
    draw.text((20, 140), "Queue Position:", fill="black", font=label_font2)

    pos_font = ImageFont.load_default(size=96)
    text = str(position)
    bbox = draw.textbbox((0, 0), text, font=pos_font)
    x = (600 - (bbox[2] - bbox[0])) // 2
    draw.text((x, 200), text, fill="black", font=pos_font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# QueueInfo model  (no ollama needed)
# ---------------------------------------------------------------------------


class TestQueueInfo:
    def test_has_position_field(self):
        info = QueueInfo(position=1, server_name="test")
        assert info.position == 1

    def test_has_server_name_field(self):
        info = QueueInfo(position=1, server_name="test")
        assert info.server_name == "test"

    def test_position_must_be_int(self):
        with pytest.raises(Exception):
            QueueInfo(position="not a number", server_name="test")

    def test_server_name_must_be_str(self):
        with pytest.raises(Exception):
            QueueInfo(position=1, server_name=42)


# ---------------------------------------------------------------------------
# Inference.__init__  (no ollama needed)
# ---------------------------------------------------------------------------


class TestInferenceInit:
    def test_default_model(self):
        assert Inference().model == MODEL

    def test_default_prompt_is_set(self):
        assert Inference().prompt == QUEUE_PROMPT

    def test_default_prompt_is_not_empty(self):
        assert len(Inference().prompt) > 0

    def test_custom_model(self):
        assert Inference(model="llama3.2-vision").model == "llama3.2-vision"

    def test_custom_prompt(self):
        assert Inference(prompt="how many fingers?").prompt == "how many fingers?"

    def test_model_and_prompt_are_independent(self):
        inf = Inference(model="x", prompt="y")
        assert inf.model == "x"
        assert inf.prompt == "y"


# ---------------------------------------------------------------------------
# Inference.run  (requires ollama + gemma4:e4b)
# ---------------------------------------------------------------------------


class TestInferenceRun:
    def test_returns_queue_info(self):
        result = Inference().run(_make_queue_image(5, "Alpha Server"))
        assert isinstance(result, QueueInfo)

    def test_position_is_int(self):
        result = Inference().run(_make_queue_image(5, "Alpha Server"))
        assert isinstance(result.position, int)

    def test_server_name_is_str(self):
        result = Inference().run(_make_queue_image(5, "Alpha Server"))
        assert isinstance(result.server_name, str)

    def test_server_name_is_not_empty(self):
        result = Inference().run(_make_queue_image(5, "Alpha Server"))
        assert result.server_name

    def test_reads_single_digit_position(self):
        result = Inference().run(_make_queue_image(7, "Alpha Server"))
        assert result.position == 7

    def test_reads_two_digit_position(self):
        result = Inference().run(_make_queue_image(42, "Alpha Server"))
        assert result.position == 42

    def test_reads_three_digit_position(self):
        result = Inference().run(_make_queue_image(137, "Alpha Server"))
        assert result.position == 137

    def test_reads_server_name(self):
        result = Inference().run(_make_queue_image(1, "Alpha Server"))
        assert "alpha" in result.server_name.lower()


# ---------------------------------------------------------------------------
# Real Arma Reforger queue screenshot
# Expected: position=9, server=[RU] #1 | ARMA-RUSSIAN.RU | RUSSIAN SERVER | VANILLA CONFLICT EVERON
# ---------------------------------------------------------------------------


class TestRealQueueScreenshot:
    @pytest.fixture(scope="class")
    def result(self):
        return Inference().run(QUEUE_TEST_IMAGE.read_bytes())

    def test_position_is_9(self, result):
        assert result.position == 9

    def test_server_name_is_not_empty(self, result):
        assert result.server_name

    def test_server_name_contains_ru_tag(self, result):
        assert "ru" in result.server_name.lower()

    def test_is_arma_returns_true(self):
        assert Inference().is_arma(QUEUE_TEST_IMAGE.read_bytes()) is True


# ---------------------------------------------------------------------------
# is_arma on a non-Arma screen (real desktop screenshot)
# ---------------------------------------------------------------------------


class TestIsArmaDetection:
    def test_plain_image_is_not_arma(self):
        img = Image.new("RGB", (400, 300), color=(200, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        assert Inference().is_arma(buf.getvalue()) is False


# ---------------------------------------------------------------------------
# ScreenState model  (no ollama needed)
# ---------------------------------------------------------------------------


class TestScreenState:
    def test_has_in_queue_field(self):
        s = ScreenState(in_queue=True, in_game=False, position=5, server_name="x")
        assert s.in_queue is True

    def test_has_in_game_field(self):
        s = ScreenState(in_queue=False, in_game=True, position=0, server_name="")
        assert s.in_game is True

    def test_has_position_field(self):
        assert ScreenState(in_queue=True, in_game=False, position=9, server_name="x").position == 9

    def test_has_server_name_field(self):
        assert ScreenState(in_queue=True, in_game=False, position=1, server_name="srv").server_name == "srv"

    def test_mutually_exclusive_states_allowed(self):
        # Model might return both false (e.g. server browser) — that's valid
        s = ScreenState(in_queue=False, in_game=False, position=0, server_name="")
        assert s.in_queue is False and s.in_game is False


# ---------------------------------------------------------------------------
# get_screen_state — integration tests (requires ollama + gemma4:e4b)
# ---------------------------------------------------------------------------


class TestGetScreenState:
    @pytest.fixture(scope="class")
    def queue_state(self):
        return Inference().get_screen_state(QUEUE_TEST_IMAGE.read_bytes())

    def test_queue_screenshot_in_queue(self, queue_state):
        assert queue_state.in_queue is True

    def test_queue_screenshot_not_in_game(self, queue_state):
        assert queue_state.in_game is False

    def test_queue_screenshot_position(self, queue_state):
        assert queue_state.position == 9

    def test_queue_screenshot_server_name_not_empty(self, queue_state):
        assert queue_state.server_name

    def test_queue_screenshot_server_name_contains_arma(self, queue_state):
        assert "arma" in queue_state.server_name.lower()

    def test_plain_image_not_in_queue(self):
        img = Image.new("RGB", (400, 300), color=(200, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        state = Inference().get_screen_state(buf.getvalue())
        assert state.in_queue is False

    def test_plain_image_not_in_game(self):
        img = Image.new("RGB", (400, 300), color=(200, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        state = Inference().get_screen_state(buf.getvalue())
        assert state.in_game is False
