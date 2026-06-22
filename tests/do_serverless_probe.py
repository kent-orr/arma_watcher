"""Throwaway probe: send the test queue screenshot to DO serverless Nemotron VL."""
import base64
import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# minimal .env loader
for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

KEY = os.environ["DO_SERVERLESS_KEY"]
MODEL = "nemotron-nano-12b-v2-vl"
URL = "https://inference.do-ai.run/v1/chat/completions"

PROMPT = (
    "Analyze this Arma Reforger screenshot and determine the current state. "
    "Set in_queue=true if a queue waiting screen is visible with a numbered position. "
    "Set in_game=true if the player is in an active game session with HUD visible. "
    "Set position to the integer queue position if in_queue, else 0. "
    "Set server_name to the server name text if in_queue, else empty string. "
    'Respond ONLY with JSON: {"in_queue":bool,"in_game":bool,"position":int,"server_name":str}'
)

img_b64 = base64.b64encode((ROOT / "tests" / "queue_test.png").read_bytes()).decode()

payload = {
    "model": MODEL,
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
        ],
    }],
    "temperature": 0,
}

req = urllib.request.Request(
    URL,
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
)

t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()[:800]}")
    raise SystemExit(1)

dt = time.time() - t0
print(f"latency: {dt:.2f}s")
print("content:", body["choices"][0]["message"]["content"])
print("usage:", json.dumps(body.get("usage", {})))
