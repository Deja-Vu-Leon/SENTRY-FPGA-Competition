"""OpenCV-style reader for the FPGA DMA service's decoded camera endpoints."""

from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen

import cv2
import numpy as np


class FpgaCapture:
    def __init__(self, source, *, jpeg_reduction=1):
        self.endpoint = urlsplit(source)
        self.query = parse_qs(self.endpoint.query)
        self.serial = "0"
        self.timestamp_ms = None
        self.jpeg_decode = {1: cv2.IMREAD_COLOR, 2: cv2.IMREAD_REDUCED_COLOR_2,
                            4: cv2.IMREAD_REDUCED_COLOR_4}[jpeg_reduction]
        self.pending = None
        self.error = ""
        self.opened = False
        if self.endpoint.path != "/frame" or self.query.get("cam") not in (["0"], ["1"]):
            self.error = "Expected /frame?cam=0 or /frame?cam=1"
            return
        ok, self.pending = self._fetch()
        self.opened = ok

    def _fetch(self):
        query = dict(self.query, s=["0"], after=[self.serial])
        url = urlunsplit(self.endpoint._replace(query=urlencode(query, doseq=True)))
        try:
            for _ in range(3):
                with urlopen(url, timeout=3) as response:
                    if response.status == 204:
                        continue
                    serial = response.headers.get("X-Serial")
                    if not serial or not serial.isdecimal() or int(serial) <= int(self.serial):
                        continue
                    self.serial = serial
                    timestamp = response.headers.get("X-T")
                    payload = response.read()
                if payload:
                    flags = self.jpeg_decode if payload.startswith(b"\xff\xd8") else cv2.IMREAD_COLOR
                    image = cv2.imdecode(np.frombuffer(payload, np.uint8), flags)
                    if image is not None:
                        try:
                            self.timestamp_ms = float(timestamp)
                        except (TypeError, ValueError):
                            self.timestamp_ms = None
                        return True, image
            self.error = "No new decodable FPGA camera frame"
        except (OSError, URLError, cv2.error) as exc:
            self.error = str(exc)
        return False, None

    def isOpened(self):
        return self.opened

    def read(self):
        if not self.opened:
            return False, None
        if self.pending is not None:
            image, self.pending = self.pending, None
            return True, image
        return self._fetch()

    def get(self, prop):
        return 0.0

    def release(self):
        self.opened = False
        self.pending = None
