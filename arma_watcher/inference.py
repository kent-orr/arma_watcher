import base64
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable

import ollama
from ollama import chat, generate
from pydantic import BaseModel

MODEL = "qwen3.5:9b"


def _installed_models() -> set[str]:
    """Return the set of model tags Ollama currently has pulled locally."""
    names: set[str] = set()
    for m in getattr(ollama.list(), "models", None) or []:
        name = getattr(m, "model", None) or getattr(m, "name", None)
        if name:
            names.add(name)
    return names


def ensure_model(model: str, log: Callable[[str], None]) -> None:
    """Make sure `model` is pulled locally, downloading it (with progress) if not.

    Raises ConnectionError / ollama.ResponseError if Ollama is unreachable so the
    caller's retry logic can handle a not-yet-started Ollama.
    """
    if model in _installed_models():
        return
    log(f"Model {model} is not installed yet. Downloading now — this can take several minutes...")
    last_status = ""
    for prog in ollama.pull(model, stream=True):
        status = getattr(prog, "status", "") if not isinstance(prog, dict) else prog.get("status", "")
        if status and status != last_status:
            log(f"  {status}")
            last_status = status
    log(f"Model {model} ready.")

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


def _parse(content: str) -> QueueInfo:
    try:
        return QueueInfo.model_validate_json(_coerce_json(content))
    except Exception:
        pass
    # Fallback: salvage position from bare integer response; server_name unknown
    match = re.search(r"\d+", content)
    position = int(match.group()) if match else 0
    return QueueInfo(position=position, server_name="")


def _coerce_json(content: str) -> str:
    """Best-effort: return the substring spanning the first '{' to the last '}'.

    Local Ollama replies are schema-constrained and already clean; cloud replies
    may carry stray prose or whitespace, so trim to the JSON object before parsing.
    """
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return content[start:end + 1]
    return content


class OllamaInference:
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
        return _parse(response.message.content)

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

    def unload(self) -> None:
        """Evict the model from Ollama VRAM immediately (keep_alive=0)."""
        generate(model=self.model, keep_alive=0)


# Backwards-compatible alias: existing callers import `Inference`.
Inference = OllamaInference


class CloudAuthError(RuntimeError):
    """Subscription is missing, inactive, or the session token cannot be obtained."""


class CloudRateLimitError(RuntimeError):
    """The proxy is rate limiting requests (HTTP 429)."""


class CloudInference:
    """Vision inference via the subscription proxy (separate repo).

    Stores the purchase email, exchanges it for a short-lived opaque session
    token at ``/token``, and posts OpenAI-style vision requests to
    ``/v1/chat/completions``. The proxy injects the model + DigitalOcean key.
    """

    def __init__(self, proxy_url: str | None, subscription_email: str | None, model: str | None = None):
        self.proxy_url = (proxy_url or "").rstrip("/")
        self.email = subscription_email
        self._token: str | None = None

    # -- HTTP helpers -------------------------------------------------------

    def _ensure_token(self) -> str:
        if self._token:
            return self._token
        req = urllib.request.Request(
            f"{self.proxy_url}/token",
            data=json.dumps({"email": self.email}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "ArmaWatcher/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code in (402, 403):
                raise CloudAuthError(
                    f"No active subscription for {self.email!r}. Check the email in Settings."
                ) from e
            raise ConnectionError(f"token endpoint error {e.code}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"cannot reach proxy at {self.proxy_url}: {e.reason}") from e
        self._token = body["token"]
        return self._token

    def _chat(self, prompt: str, image_bytes: bytes, schema: dict) -> str:
        instruction = (
            prompt
            + " Respond ONLY with JSON matching this schema: "
            + json.dumps(schema)
        )
        img_b64 = base64.b64encode(image_bytes).decode()
        data = json.dumps({
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                ],
            }],
            "max_tokens": 256,
            "temperature": 0,
        }).encode()

        # Two attempts: a stale token gets refreshed once on 401/403.
        for attempt in range(2):
            token = self._ensure_token()
            req = urllib.request.Request(
                f"{self.proxy_url}/v1/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "ArmaWatcher/1.0",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    body = json.loads(resp.read())
                return body["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                if e.code in (401, 403) and attempt == 0:
                    self._token = None  # stale token — refresh and retry once
                    continue
                if e.code in (401, 402, 403):
                    raise CloudAuthError(
                        "Subscription invalid or expired — check the email in Settings."
                    ) from e
                if e.code == 429:
                    raise CloudRateLimitError("rate limited by inference proxy") from e
                raise ConnectionError(f"proxy inference error {e.code}") from e
            except urllib.error.URLError as e:
                raise ConnectionError(f"cannot reach proxy at {self.proxy_url}: {e.reason}") from e
        raise CloudAuthError("Authentication failed after refreshing the session token.")

    # -- Same interface as OllamaInference ---------------------------------

    def run(self, image_bytes: bytes) -> QueueInfo:
        return _parse(self._chat(QUEUE_PROMPT, image_bytes, QueueInfo.model_json_schema()))

    def is_arma(self, image_bytes: bytes) -> bool:
        content = self._chat(DETECT_PROMPT, image_bytes, _ArmaDetection.model_json_schema())
        try:
            return _ArmaDetection.model_validate_json(_coerce_json(content)).is_arma
        except Exception:
            return False

    def get_screen_state(self, image_bytes: bytes) -> ScreenState:
        content = self._chat(SCREEN_STATE_PROMPT, image_bytes, ScreenState.model_json_schema())
        try:
            return ScreenState.model_validate_json(_coerce_json(content))
        except Exception:
            return ScreenState(in_queue=False, in_game=False, position=0, server_name="")

    def unload(self) -> None:
        """No-op — nothing runs locally in cloud mode."""


def make_inference(cfg: dict, model: str | None = None):
    """Return the inference backend selected by `cfg["inference_mode"]`."""
    if cfg.get("inference_mode") == "cloud":
        return CloudInference(
            proxy_url=cfg.get("proxy_url"),
            subscription_email=cfg.get("subscription_email"),
        )
    return OllamaInference(model=model or cfg.get("model", MODEL))
