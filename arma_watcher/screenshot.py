import io

import mss
from PIL import Image


def list_monitors() -> list[dict]:
    """Return all monitors. Index 0 is the virtual all-monitors canvas; 1+ are physical monitors."""
    with mss.MSS() as sct:
        return list(sct.monitors)


def capture_monitor(monitor_index: int) -> Image.Image:
    with mss.MSS() as sct:
        monitors = sct.monitors
        if monitor_index < 0 or monitor_index >= len(monitors):
            raise ValueError(
                f"Monitor index {monitor_index} out of range. "
                f"Valid: 0-{len(monitors) - 1} (0 = all monitors combined, 1+ = individual)"
            )
        shot = sct.grab(monitors[monitor_index])
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def capture_to_bytes(monitor_index: int, fmt: str = "PNG") -> bytes:
    img = capture_monitor(monitor_index)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()
