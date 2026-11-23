"""Replay demonstration assets on RK without using the live capture or alert directory."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import cv2
from cockpit_worker import CAMERAS, DriverEyes, RoadSurface, SlopeMotion, FIRST
from cockpit_alert_archive import AlertArchive
from vision import NativeObjectDetector


def replay(path, analyze):
    capture = cv2.VideoCapture(str(path))
    fps = capture.get(cv2.CAP_PROP_FPS)
    count = 0
    first = None
    try:
        if fps <= 0:
            raise ValueError(f"unreadable demo: {path}")
        while True:
            ok, frame = capture.read()
            if not ok:
                return count, first
            boxes = analyze(frame, count/fps)
            if boxes and first is None:
                first = frame, boxes[0]
            count += 1
    finally:
        capture.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media", type=Path)
    args = parser.parse_args()
    models = (DriverEyes(), SlopeMotion(), RoadSurface())
    checks = (("A02/simulated-prolonged-eye-closure.mp4", lambda f,t: models[0](f,t)[0], 1, "疑似持续闭眼"),
              ("B01/simulated-slope-motion.mp4", lambda f,t: models[1](f), 2, "疑似土石扰动"),
              ("B02/simulated-asphalt-crack.mp4", lambda f,t: models[2](f), 3, "疑似道路裂缝"))
    failures = 0
    cv2.setNumThreads(1)
    with TemporaryDirectory() as directory:
        archive = AlertArchive(directory)
        for path, analyze, channel, reason in checks:
            count, sample = replay(args.media/path, analyze)
            print(f"{CAMERAS[channel]} {path}: {count} frames, alert={sample is not None}", flush=True)
            if sample is None:
                failures += 1
                continue
            frame, bounds = sample
            archive.save(CAMERAS[channel], frame, SimpleNamespace(box=bounds, score=None),
                         SimpleNamespace(reason=reason, distance_m=None))
        detector = NativeObjectDetector(FIRST/"rk_yolo_srv", FIRST/"yolov8n.rknn", 0, classes={0:"person"})
        try:
            found = 0
            for path in sorted((args.media/"B01").glob("role-person-*.jpg")):
                image = cv2.imread(str(path))
                if image is not None:
                    found += len(detector.detect(cv2.resize(image,(420,236))))
            print(f"B01 NPU: {found} pedestrian detections", flush=True)
            failures += found==0
        finally:
            detector.close()
        print(f"Function 4 test: {len(list(Path(directory).glob('*.jpg')))} snapshots with event metadata")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
