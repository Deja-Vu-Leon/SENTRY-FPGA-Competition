"""Local danger-event log and annotated screenshot storage."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import cv2


class EventLogger:
    def __init__(self, directory, cooldown_s=3.0, max_mb=512):
        if cooldown_s < 0 or max_mb <= 0:
            raise ValueError("invalid log limits")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.events_path = self.directory / "events.jsonl"
        self.cooldown_s = cooldown_s
        self.max_bytes = int(max_mb * 1024 * 1024)
        self.last_by_reason = {}
        self.sequence = 0

    def record(self, kind, details=None, screenshot=None, cooldown_key=None):
        now = time.monotonic()
        if cooldown_key is not None:
            last = self.last_by_reason.get(cooldown_key, float("-inf"))
            if now-last < self.cooldown_s:
                return None
        timestamp = datetime.now(timezone.utc)
        event = {"time_utc": timestamp.isoformat(), "kind": kind, "details": details or {}}
        if screenshot is not None:
            self.sequence += 1
            filename = f"danger_{timestamp.strftime('%Y%m%dT%H%M%S_%f')}_{self.sequence:04d}.jpg"
            path = self.directory / filename
            ok, encoded = cv2.imencode(".jpg", screenshot, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if not ok:
                raise OSError("JPEG encoding failed")
            path.write_bytes(encoded.tobytes())
            event["image"] = filename
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        if cooldown_key is not None:
            self.last_by_reason[cooldown_key] = now
        if screenshot is not None:
            self._prune_images()
        return event

    def _prune_images(self):
        images = sorted(self.directory.glob("danger_*.jpg"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in images)
        for path in images[:-1]:
            if total <= self.max_bytes:
                break
            size = path.stat().st_size
            path.unlink()
            total -= size
