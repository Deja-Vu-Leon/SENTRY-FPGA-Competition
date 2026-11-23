"""Persist high-risk vehicle observations and their inference-time images."""
from datetime import datetime
import json
from pathlib import Path
import time
import uuid

import cv2


class AlertArchive:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o750, parents=True, exist_ok=True)
        self.last = {}

    def save(self, port, frame, detection, risk):
        key = (port, risk.reason)
        now = time.monotonic()
        if now - self.last.get(key, -999) < 5:
            return
        stamp = datetime.now().astimezone()
        identifier = uuid.uuid4().hex
        image = frame.copy()
        x1, y1, x2, y2 = detection.box
        cv2.rectangle(image, (x1, y1), (x2, y2), (80, 80, 255), 2)
        result, jpeg = cv2.imencode(".jpg", image)
        if not result:
            raise OSError("Could not encode alert image")
        (self.directory / (identifier + ".jpg")).write_bytes(jpeg.tobytes())
        xrgb = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
        (self.directory / (identifier + ".xrgb")).write_bytes(xrgb.tobytes())
        event = dict(id=identifier, camera=port, timestamp=stamp.isoformat(),
                     confidence=detection.score, reason=risk.reason,
                     distance_m=risk.distance_m, image=identifier + ".jpg")
        path = self.directory / (identifier + ".json")
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)
        index = self.directory / "index.tsv"
        try:
            old = index.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            old = []
        reason = {"距离过近": 1, "快速接近": 2}.get(risk.reason, 0)
        row = f'{identifier}.xrgb {port} {stamp:%m-%dT%H:%M:%S%z} {round(detection.score * 100)} {reason}'
        temp = index.with_suffix(".tmp")
        temp.write_text("\n".join([row, *old[:23]]) + "\n", encoding="utf-8")
        temp.replace(index)
        self.last[key] = now
