"""Four independent camera roles using the first RK release's detector and ranging."""
import argparse
import ctypes as ct
import json
import mmap
import os
from pathlib import Path
import signal
import struct
import sys
import time

import cv2
import numpy as np

FIRST = Path("/home/linaro/sentry-dual")
sys.path.insert(0, str(FIRST))
from vision import NativeObjectDetector, RKNNDetector
from vehicle_risk import VehicleMonitor, filter_vehicle_duplicates

PORTS = ("A0", "A1", "B0", "B1")
W, H = 420, 236
IMAGE_BYTES = W * H * 4
INPUT = IMAGE_BYTES + 4
OUTPUT = 816
SIZE = 4 * (INPUT + OUTPUT)
BOX = struct.Struct("<iiiiI44s")
EXCHANGE = "/run/sentry-vid007-ai/exchange"
VEHICLES = RKNNDetector.VEHICLE_CLASSES
PERSON = {0: "person"}
ROLES = (VEHICLES, VEHICLES, PERSON, PERSON)
COLORS = {"high": 0xff5555, "caution": 0xffbd4a, "normal": 0x44e3ae, "unknown": 0xffdb80}
running = True

def halt(*_):
    global running
    running = False

class Exchange:
    def __init__(self):
        fd = os.open(EXCHANGE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            os.ftruncate(fd, SIZE)
            self.mem = mmap.mmap(fd, SIZE)
        finally:
            os.close(fd)
        self.address = ct.addressof(ct.c_char.from_buffer(self.mem))
        lib = ct.CDLL("libatomic.so.1")
        self.load = getattr(lib, "__atomic_load_4")
        self.load.argtypes = (ct.c_void_p, ct.c_int)
        self.load.restype = ct.c_uint32
        self.store = getattr(lib, "__atomic_store_4")
        self.store.argtypes = (ct.c_void_p, ct.c_uint32, ct.c_int)
        self.store.restype = None

    def frame(self, ch, previous):
        offset = ch * INPUT
        addr = self.address + offset
        seq = self.load(addr, 5)
        if not seq or seq & 1 or seq == previous:
            return previous, None
        pixels = self.mem[offset+4:offset+INPUT]
        if self.load(addr, 5) != seq:
            return previous, None
        xrgb = np.frombuffer(pixels, np.uint8).reshape(H, W, 4)
        return seq, cv2.cvtColor(xrgb, cv2.COLOR_BGRA2BGR)

    def publish(self, ch, boxes, status):
        offset = 4 * INPUT + ch * OUTPUT
        addr = self.address + offset
        seq = (self.load(addr, 5) + 2) & 0xfffffffe
        self.store(addr, (seq - 1) & 0xffffffff, 5)
        struct.pack_into("<IQ", self.mem, offset+4, len(boxes), time.monotonic_ns()+650_000_000)
        for i, (coords, color, label) in enumerate(boxes):
            BOX.pack_into(self.mem, offset+16+i*BOX.size, *coords, color, label.encode()[:43])
        struct.pack_into("<32s", self.mem, offset+16+12*BOX.size, status.encode()[:31])
        self.store(addr, seq, 5)

def open_detector(classes):
    return NativeObjectDetector(FIRST / "rk_yolo_srv", FIRST / "yolov8n.rknn", 0,
                                classes=classes)

def objects(detector, frame, ch, monitor, timestamp):
    detector.classes = ROLES[ch]
    detections = detector.detect(frame)
    if monitor:
        detections = filter_vehicle_duplicates(detections)
        risks = monitor.update(detections, W, timestamp, measured=True)
    else:
        risks = {}
    boxes = []
    for i, det in enumerate(detections[:12]):
        risk = risks.get(i)
        label = f"{det.label} {det.score:.0%}"
        color = 0x6ab8ff
        if risk is not None:
            color = COLORS[risk.level]
            if risk.distance_m is not None:
                label = f"{det.label} ~{risk.distance_m:.1f}m"
                if risk.closing_kmh is not None and abs(risk.closing_kmh) >= 2:
                    label += f" {risk.closing_kmh:+.0f}km/h"
                if risk.level == "high":
                    label += " ALERT"
        boxes.append((det.box, color, label))
    return boxes

def smoke(detector):
    road = cv2.VideoCapture(str(FIRST / "media/highway.mp4"))
    try:
        for ch in (0, 1):
            monitor = VehicleMonitor(.9, 10.)
            found = []
            for step in range(28):
                ok, frame = road.read()
                if not ok:
                    break
                boxes = objects(detector, cv2.resize(frame, (W,H)), ch, monitor, step*.12)
                found.extend(label for _, _, label in boxes if "~" in label)
            if not found:
                raise RuntimeError(f"{PORTS[ch]} no vehicle distance on road sample")
            print(PORTS[ch], "recorded road sample:", ", ".join(found[:5]), flush=True)
    finally:
        road.release()
    for ch in (2, 3):
        labels = []
        for source in sorted((FIRST / "staging").glob("role-person-*.jpg")):
            frame = cv2.imread(str(source))
            if frame is not None:
                labels.extend(label for _, _, label in objects(
                    detector, cv2.resize(frame, (W,H)), ch, None, time.monotonic()))
        if not labels:
            raise RuntimeError(f"{PORTS[ch]} no pedestrian on recorded samples")
        print(PORTS[ch], "recorded pedestrian samples:", ", ".join(labels[:5]), flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--a0-focal", type=float, default=.9)
    parser.add_argument("--a1-focal", type=float, default=.9)
    args = parser.parse_args()
    if not all(.1 <= x <= 10 for x in (args.a0_focal,args.a1_focal)):
        parser.error("focal ratios must be in [0.1,10]")
    signal.signal(signal.SIGINT, halt)
    signal.signal(signal.SIGTERM, halt)
    cv2.setNumThreads(1)
    exchange = None if args.smoke else Exchange()
    detector = open_detector(VEHICLES)
    try:
        if args.smoke:
            smoke(detector)
            return
        monitors = (VehicleMonitor(args.a0_focal,10.), VehicleMonitor(args.a1_focal,10.), None, None)
        sequence = [0]*4
        counts = [0]*4
        seen = [0]*4
        recent = [[] for _ in PORTS]
        last = time.monotonic()
        print("ready: A0/A1 vehicle detection + approximate monocular range; B0/B1 pedestrians", flush=True)
        while running:
            worked = False
            for ch in range(4):
                sequence[ch], frame = exchange.frame(ch, sequence[ch])
                if frame is None:
                    continue
                worked = True
                captured = time.monotonic()
                if monitors[ch] and captured-seen[ch] > .6:
                    monitors[ch].reset()
                seen[ch] = captured
                boxes = objects(detector,frame,ch,monitors[ch],captured)
                counts[ch] += 1
                recent[ch] = [label for _, _, label in boxes]
                role = "Vehicles" if ch < 2 else "Pedestrians"
                exchange.publish(ch,boxes,f"{role}: {len(boxes)}")
            now = time.monotonic()
            if now-last >= 5:
                print(json.dumps({port: {"infer_fps":round(counts[i]/(now-last),2),
                                       "live":now-seen[i]<1,
                                       "objects":recent[i] if now-seen[i]<1 else []}
                                  for i,port in enumerate(PORTS)}), flush=True)
                counts = [0]*4
                last = now
            if not worked:
                time.sleep(.008)
    finally:
        detector.close()

if __name__ == "__main__":
    main()
