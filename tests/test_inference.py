"""
Tests for src/inference.py.

Init tests are pure unit tests (no ollama required).
Run tests hit the real ollama stack — ollama must be running with the model under
test loaded. Select it with `--model <tag>` or $ARMA_WATCHER_TEST_MODEL (see
conftest.py); both default to inference.MODEL (qwen3.5:9b).
"""
import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from arma_watcher.inference import (
    CLOUD_MAX_EDGE,
    MODEL,
    QUEUE_PROMPT,
    Inference,
    QueueInfo,
    Screen,
    ScreenState,
    _downscale_for_cloud,
)

_HERE = Path(__file__).parent

# The four real Arma Reforger screens, in progression order. Every one of these is
# Arma (is_arma → True); they differ only by which `screen` the classifier should pick.
QUEUE_TEST_IMAGE = _HERE / "queue_test.png"                      # the queue modal, position 9
SPLASH_IMAGE = _HERE / "queue_test_splash.png"                   # loading/title screen
MAIN_MENU_IMAGE = _HERE / "queue_test_main_menu.png"            # main menu tiles
SERVER_BROWSER_IMAGE = _HERE / "queue_test_server_browser.png"  # server list, the queue's near-twin

# Screens whose exact `screen` label we pin. server_browser vs in_queue is the
# load-bearing case: the queue is a modal drawn on top of the browser, so those two
# images are ~80% identical pixels — the classifier must still separate them.
# (The splash screen is deliberately absent here: lightweight models file its dark
# cinematic art under 'other' rather than 'splash'. That's harmless — it still reads as
# a non-queue/non-game "keep waiting" screen, which is asserted in WAITING_IMAGES below.)
EXACT_SCREEN_CASES = [
    (MAIN_MENU_IMAGE, Screen.MAIN_MENU),
    (SERVER_BROWSER_IMAGE, Screen.SERVER_BROWSER),
    (QUEUE_TEST_IMAGE, Screen.IN_QUEUE),
]

# Non-queue Arma screens. Whatever exact label the model picks, the safety property the
# watcher relies on is the same: none of these may read as in_queue or in_game, or the
# watcher would falsely fire "you're in the queue!" while the user is still in menus.
WAITING_IMAGES = [SPLASH_IMAGE, MAIN_MENU_IMAGE, SERVER_BROWSER_IMAGE]

# All real Arma screens — is_arma must be True on every one of them.
REAL_ARMA_IMAGES = [SPLASH_IMAGE, MAIN_MENU_IMAGE, SERVER_BROWSER_IMAGE, QUEUE_TEST_IMAGE]


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


def _non_arma_png() -> bytes:
    """A realistic non-Arma screenshot — a text-editor window on a desktop.

    The negative case for is_arma / screen detection. A real desktop monitor shows
    recognizable content like this, not a featureless rectangle, so it's both a fairer
    test and one a lightweight vision model can actually judge (a blank fill is
    out-of-distribution and gets guessed as Arma).
    """
    img = Image.new("RGB", (960, 600), (45, 48, 56))                # desktop bg
    d = ImageDraw.Draw(img)
    d.rectangle([80, 60, 880, 540], fill=(250, 250, 250))           # window
    d.rectangle([80, 60, 880, 96], fill=(220, 220, 220))            # title bar
    title_font = ImageFont.load_default(size=20)
    body_font = ImageFont.load_default(size=16)
    d.text((96, 68), "Untitled Document - Text Editor", fill=(20, 20, 20), font=title_font)
    lines = [
        "Dear team,", "", "Please find attached the quarterly report.",
        "Let me know if you have any questions about the", "figures in section 3.",
        "", "Best regards,", "Alex",
    ]
    for i, line in enumerate(lines):
        d.text((110, 130 + i * 34), line, fill=(30, 30, 30), font=body_font)
    d.rectangle([0, 568, 960, 600], fill=(28, 30, 36))              # taskbar
    d.text((12, 575), "Start    Files    Browser    Mail", fill=(210, 210, 210), font=body_font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Repeated-sampling harness for the (non-deterministic) vision integration tests
# ---------------------------------------------------------------------------
# Vision inference isn't deterministic, so one unlucky roll shouldn't fail the
# suite and one lucky roll shouldn't pass it. Each scenario is sampled N_RUNS
# times and an assertion passes when at least PASS_RATE of the samples hold.

N_RUNS = 10
PASS_RATE = 0.9


def _sample(fn, n=N_RUNS):
    """Run `fn` (one inference call) `n` times; return the list of results."""
    return [fn() for _ in range(n)]


def assert_rate(samples, predicate, msg, rate=PASS_RATE):
    """Pass when `predicate` holds for at least `rate` of `samples`."""
    hits = sum(1 for s in samples if predicate(s))
    n = len(samples)
    assert hits >= rate * n, f"{msg}: {hits}/{n} samples passed (need >={rate:.0%})"


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
# _downscale_for_cloud  (no ollama needed) — guards the cloud image-size fix
# ---------------------------------------------------------------------------


def _png_bytes(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(30, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


class TestDownscaleForCloud:
    def test_oversized_image_is_capped_to_max_edge(self):
        out = _downscale_for_cloud(_png_bytes(3840, 2160))
        assert max(Image.open(io.BytesIO(out)).size) == CLOUD_MAX_EDGE

    def test_aspect_ratio_is_preserved(self):
        out = _downscale_for_cloud(_png_bytes(3840, 2160))
        w, h = Image.open(io.BytesIO(out)).size
        assert round(w / h, 2) == round(3840 / 2160, 2)

    def test_output_is_jpeg(self):
        assert Image.open(io.BytesIO(_downscale_for_cloud(_png_bytes(800, 600)))).format == "JPEG"

    def test_small_image_is_not_upscaled(self):
        out = _downscale_for_cloud(_png_bytes(640, 480))
        assert Image.open(io.BytesIO(out)).size == (640, 480)

    def test_undecodable_bytes_fall_back_to_input(self):
        assert _downscale_for_cloud(b"not an image") == b"not an image"


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
# Inference.run  (requires ollama + the model under test)
# ---------------------------------------------------------------------------


class TestInferenceRun:
    @pytest.fixture(scope="class")
    def alpha5(self, inference):
        img = _make_queue_image(5, "Alpha Server")
        return _sample(lambda: inference.run(img))

    def test_returns_queue_info(self, alpha5):
        assert_rate(alpha5, lambda r: isinstance(r, QueueInfo), "run returns QueueInfo")

    def test_position_is_int(self, alpha5):
        assert_rate(alpha5, lambda r: isinstance(r.position, int), "position is int")

    def test_server_name_is_str(self, alpha5):
        assert_rate(alpha5, lambda r: isinstance(r.server_name, str), "server_name is str")

    def test_server_name_is_not_empty(self, alpha5):
        assert_rate(alpha5, lambda r: bool(r.server_name), "server_name is non-empty")

    @pytest.mark.parametrize("position", [7, 42, 137])
    def test_reads_position(self, inference, position):
        img = _make_queue_image(position, "Alpha Server")
        samples = _sample(lambda: inference.run(img))
        assert_rate(samples, lambda r: r.position == position, f"reads position {position}")

    def test_reads_server_name(self, inference):
        img = _make_queue_image(1, "Alpha Server")
        samples = _sample(lambda: inference.run(img))
        assert_rate(samples, lambda r: "alpha" in r.server_name.lower(), "reads server name 'alpha'")


# ---------------------------------------------------------------------------
# Real Arma Reforger queue screenshot
# Expected: position=9, server=[RU] #1 | ARMA-RUSSIAN.RU | RUSSIAN SERVER | VANILLA CONFLICT EVERON
# ---------------------------------------------------------------------------


class TestRealQueueScreenshot:
    @pytest.fixture(scope="class")
    def results(self, inference):
        img = QUEUE_TEST_IMAGE.read_bytes()
        return _sample(lambda: inference.run(img))

    def test_position_is_9(self, results):
        assert_rate(results, lambda r: r.position == 9, "position is 9")

    def test_server_name_is_not_empty(self, results):
        assert_rate(results, lambda r: bool(r.server_name), "server_name is non-empty")

    def test_server_name_contains_ru_tag(self, results):
        assert_rate(results, lambda r: "ru" in r.server_name.lower(), "server_name contains 'ru'")


# ---------------------------------------------------------------------------
# is_arma — True on every real Arma screen, False on a non-Arma image
# ---------------------------------------------------------------------------


class TestIsArmaDetection:
    @pytest.mark.parametrize(
        "image_path", REAL_ARMA_IMAGES, ids=[p.stem for p in REAL_ARMA_IMAGES]
    )
    def test_real_arma_screen_is_arma(self, inference, image_path):
        img = image_path.read_bytes()
        samples = _sample(lambda: inference.is_arma(img))
        assert_rate(samples, lambda v: v is True, f"is_arma True on {image_path.stem}")

    def test_non_arma_image_is_not_arma(self, inference):
        img = _non_arma_png()
        samples = _sample(lambda: inference.is_arma(img))
        assert_rate(samples, lambda v: v is False, "is_arma False on non-Arma image")


# ---------------------------------------------------------------------------
# ScreenState model  (no ollama needed)
# ---------------------------------------------------------------------------


class TestScreenState:
    def test_screen_field_drives_in_queue(self):
        s = ScreenState(queue_dialog_visible=True, screen=Screen.IN_QUEUE, position=5, server_name="x")
        assert s.in_queue is True
        assert s.in_game is False

    def test_screen_field_drives_in_game(self):
        s = ScreenState(queue_dialog_visible=False, screen=Screen.IN_GAME, position=0, server_name="")
        assert s.in_game is True
        assert s.in_queue is False

    def test_has_position_field(self):
        s = ScreenState(queue_dialog_visible=True, screen=Screen.IN_QUEUE, position=9, server_name="x")
        assert s.position == 9

    def test_has_server_name_field(self):
        s = ScreenState(queue_dialog_visible=True, screen=Screen.IN_QUEUE, position=1, server_name="srv")
        assert s.server_name == "srv"

    @pytest.mark.parametrize("screen", [Screen.SPLASH, Screen.MAIN_MENU, Screen.SERVER_BROWSER, Screen.OTHER])
    def test_non_queue_non_game_screens_are_neither(self, screen):
        # splash / menu / browser / other are all "keep waiting" states — the
        # enum makes in_queue and in_game mutually exclusive by construction.
        s = ScreenState(queue_dialog_visible=False, screen=screen, position=0, server_name="")
        assert s.in_queue is False and s.in_game is False

    def test_screen_must_be_known_value(self):
        with pytest.raises(Exception):
            ScreenState(queue_dialog_visible=False, screen="not_a_real_screen", position=0, server_name="")


# ---------------------------------------------------------------------------
# get_screen_state — integration tests (requires ollama + the model under test)
# Each real screenshot must classify as exactly one `screen`. The server_browser
# vs in_queue split is the one that protects the watcher from a false "in queue!".
# ---------------------------------------------------------------------------


class TestGetScreenState:
    @pytest.fixture(scope="class")
    def queue_states(self, inference):
        img = QUEUE_TEST_IMAGE.read_bytes()
        return _sample(lambda: inference.get_screen_state(img))

    @pytest.fixture(scope="class")
    def non_arma_states(self, inference):
        img = _non_arma_png()
        return _sample(lambda: inference.get_screen_state(img))

    @pytest.mark.parametrize(
        "image_path, expected",
        EXACT_SCREEN_CASES,
        ids=[expected.value for _, expected in EXACT_SCREEN_CASES],
    )
    def test_screen_is_classified(self, inference, image_path, expected):
        img = image_path.read_bytes()
        samples = _sample(lambda: inference.get_screen_state(img))
        assert_rate(samples, lambda s: s.screen is expected, f"{image_path.stem} → {expected.value}")

    @pytest.mark.parametrize(
        "image_path", WAITING_IMAGES, ids=[p.stem for p in WAITING_IMAGES]
    )
    def test_non_queue_screen_is_not_in_queue_or_game(self, inference, image_path):
        # The load-bearing safety property: no menu/browser/splash screen may read as
        # in_queue (which would fire a false "you're in the queue!") or in_game.
        img = image_path.read_bytes()
        samples = _sample(lambda: inference.get_screen_state(img))
        assert_rate(samples, lambda s: not s.in_queue and not s.in_game, f"{image_path.stem} is a waiting screen")

    def test_queue_screenshot_in_queue(self, queue_states):
        assert_rate(queue_states, lambda s: s.in_queue is True, "in_queue True")

    def test_queue_screenshot_not_in_game(self, queue_states):
        assert_rate(queue_states, lambda s: s.in_game is False, "in_game False")

    def test_queue_screenshot_position(self, queue_states):
        assert_rate(queue_states, lambda s: s.position == 9, "position is 9")

    def test_queue_screenshot_server_name_not_empty(self, queue_states):
        assert_rate(queue_states, lambda s: bool(s.server_name), "server_name is non-empty")

    def test_queue_screenshot_server_name_contains_ru(self, queue_states):
        assert_rate(queue_states, lambda s: "ru" in s.server_name.lower(), "server_name contains 'ru'")

    def test_non_arma_image_not_in_queue(self, non_arma_states):
        assert_rate(non_arma_states, lambda s: s.in_queue is False, "non-Arma not in_queue")

    def test_non_arma_image_not_in_game(self, non_arma_states):
        assert_rate(non_arma_states, lambda s: s.in_game is False, "non-Arma not in_game")
