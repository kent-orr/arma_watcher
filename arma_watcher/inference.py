import re

from ollama import chat
from pydantic import BaseModel

MODEL = "gemma4:e4b"

QUEUE_PROMPT = (
    "This is a screenshot from an Arma Reforger server browser queue. "
    "Read the screen carefully and extract two values: "
    "'position' — the integer queue position number shown, "
    "'server_name' — the exact server name text shown. "
    "Both fields are required."
)

DETECT_PROMPT = (
    "Is this a screenshot of Arma Reforger (the game, its server browser, or its queue screen)? "
    "Return true if yes, false if no."
)

SCREEN_STATE_PROMPT = (
    "Analyze this Arma Reforger screenshot and determine the current state. "
    "Set in_queue=true if a queue waiting screen is visible with a numbered position. "
    "Set in_game=true if the player is in an active game session with HUD visible. "
    "Set position to the integer queue position if in_queue, else 0. "
    "Set server_name to the server name text if in_queue, else empty string."
)


class QueueInfo(BaseModel):
    position: int
    server_name: str


class ScreenState(BaseModel):
    in_queue: bool
    in_game: bool
    position: int
    server_name: str


class _ArmaDetection(BaseModel):
    is_arma: bool


class Inference:
    def __init__(self, model: str = MODEL, prompt: str = QUEUE_PROMPT):
        self.model = model
        self.prompt = prompt

    def run(self, image_bytes: bytes) -> QueueInfo:
        response = chat(
            model=self.model,
            messages=[{
                "role": "user",
                "content": self.prompt,
                "images": [image_bytes],
            }],
            format=QueueInfo.model_json_schema(),
        )
        return self._parse(response.message.content)

    def is_arma(self, image_bytes: bytes) -> bool:
        response = chat(
            model=self.model,
            messages=[{
                "role": "user",
                "content": DETECT_PROMPT,
                "images": [image_bytes],
            }],
            format=_ArmaDetection.model_json_schema(),
        )
        try:
            return _ArmaDetection.model_validate_json(response.message.content).is_arma
        except Exception:
            return False

    def get_screen_state(self, image_bytes: bytes) -> ScreenState:
        response = chat(
            model=self.model,
            messages=[{
                "role": "user",
                "content": SCREEN_STATE_PROMPT,
                "images": [image_bytes],
            }],
            format=ScreenState.model_json_schema(),
        )
        try:
            return ScreenState.model_validate_json(response.message.content)
        except Exception:
            return ScreenState(in_queue=False, in_game=False, position=0, server_name="")

    @staticmethod
    def _parse(content: str) -> QueueInfo:
        try:
            return QueueInfo.model_validate_json(content)
        except Exception:
            pass
        # Fallback: salvage position from bare integer response; server_name unknown
        match = re.search(r"\d+", content)
        position = int(match.group()) if match else 0
        return QueueInfo(position=position, server_name="")
