"""Independent latest-frame workers for the native RK cockpit."""
import signal
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from four_camera_features import Exchange, FIRST, PORTS, W, H, VEHICLES
from vision import NativeObjectDetector
from vehicle_risk import VehicleMonitor, filter_vehicle_duplicates
from video_lane import VideoLaneAnalyzer
from hazard_model import (CRACK_MODEL, CRACK_THRESHOLDS, CRACKS, SLOPE_BOX_MODEL,
                          SLOPE_THRESHOLDS, SLOPE, CorroboratedCracks, HazardModel,
                          LatestHazards, PersistentHazards)
from cockpit_alert_archive import AlertArchive
from cockpit_recorder import RecordingFrames, record_loop
from cockpit_playback import playback_loop

RUN = Path("/run/sentry-vid007-ai")
ROOT = Path(__file__).resolve().parent
DIRECTIONS = ("前方", "驾驶舱", "右侧", "左侧")
CAMERAS = ("A01", "A02", "B01", "B02")
LABEL = {"person": "行人", "car": "汽车", "truck": "货车", "bus": "客车",
         "bike": "自行车", "motorbike": "摩托车", "light": "信号灯", "cone": "障碍物"}
CLASSES = {**VEHICLES, 0: "person", 9: "light", 13: "cone", 24: "cone",
           26: "cone", 28: "cone", 56: "cone"}
VEHICLE_LABELS = frozenset(VEHICLES.values())
stop = threading.Event()
HAZARD_SETTINGS = {
    2: (*SLOPE_BOX_MODEL,SLOPE,SLOPE_THRESHOLDS,.80,("疑似滑坡堆积区","疑似滑坡源区")),
    3: (*CRACK_MODEL,CRACKS,CRACK_THRESHOLDS,.60,("纵向裂缝","横向裂缝","龟裂")),
}


def signal_color(frame, bounds):
    x, y, right, bottom = bounds
    crop = frame[y:bottom, x:right]
    if crop.size < 36:
        return "待判"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 105, 130), (12, 255, 255)) | cv2.inRange(hsv, (165, 105, 130), (179, 255, 255))
    green = cv2.inRange(hsv, (41, 90, 120), (95, 255, 255))
    yellow = cv2.inRange(hsv, (16, 115, 140), (38, 255, 255))
    counts = sorted(((cv2.countNonZero(mask), name) for mask, name in
                     ((red, "红灯"), (green, "绿灯"), (yellow, "黄灯"))), reverse=True)
    return counts[0][1] if counts[0][0] >= max(4, crop.shape[0] * crop.shape[1] * .04, counts[1][0] * 1.5) else "待判"


class DriverEyes:
    def __init__(self):
        self.face = cv2.CascadeClassifier(str(ROOT / "models/haarcascade_frontalface_default.xml"))
        self.eye = cv2.CascadeClassifier(str(ROOT / "models/haarcascade_eye_tree_eyeglasses.xml"))
        self.closed = None
        self.opened = None

    def __call__(self, frame, stamp):
        if self.face.empty() or self.eye.empty():
            return [], "缺少眼部检测模型"
        gray = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        faces = self.face.detectMultiScale(gray, 1.15, 5, minSize=(64, 64))
        if len(faces) != 1:
            self.closed = self.opened = None
            return [], "未获取单人正脸"
        x, y, w, h = map(int, faces[0])
        region = gray[y+int(h*.16):y+int(h*.61), x+int(w*.12):x+int(w*.88)]
        eyes = self.eye.detectMultiScale(region, 1.12, 5, minSize=(max(w//10, 10),)*2)
        if len(eyes) >= 2:
            self.opened, self.closed = stamp, None
            return [], "眼部可见"
        if self.closed is None:
            if self.opened is None or stamp - self.opened > 3:
                return [], "眼部证据不足"
            self.closed = stamp
        if stamp - self.closed < 1.6:
            return [], "观察闭眼持续时间"
        return [(x, y, x+w, y+h)], "疑似持续闭眼"


class RoadSurface:
    def __init__(self):
        self.last = None
        self.hits = 0

    def __call__(self, frame):
        y0 = H * 3 // 5
        road = frame[y0:]
        gray = cv2.cvtColor(road, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(road, cv2.COLOR_BGR2HSV)
        pavement = cv2.inRange(hsv, (0, 0, 58), (179, 68, 215))
        if cv2.countNonZero(pavement) < gray.size*.68:
            self.last, self.hits = None, 0
            return []
        black = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
        mask = cv2.threshold(black, 26, 255, cv2.THRESH_BINARY)[1]
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        parts = []
        for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            x,y,w,h = cv2.boundingRect(contour)
            if max(w,h)>=30 and min(w,h)>=3 and 18<=cv2.contourArea(contour)<=w*h*.35:
                parts.append((x,y+y0,x+w,y+y0+h))
        found = max(parts, key=lambda b:(b[2]-b[0])+(b[3]-b[1]), default=None)
        self.hits = self.hits+1 if found and self.last and abs(found[0]-self.last[0])+abs(found[1]-self.last[1])<55 else 0
        self.last = found
        return [found] if found and self.hits>=3 else []


class SlopeMotion:
    def __init__(self):
        self.previous = None
        self.hits = 0

    def __call__(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        old, self.previous = self.previous, gray
        if old is None:
            return []
        # Reject global camera motion, retain localized motion in earth-colored regions.
        delta = cv2.absdiff(old, gray)
        if np.mean(delta > 24) > .16:
            self.hits = 0
            return []
        soil = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), (3, 43, 35), (35, 235, 240))
        motion = cv2.bitwise_and(cv2.threshold(delta, 24, 255, cv2.THRESH_BINARY)[1], soil)
        motion = cv2.morphologyEx(motion, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        candidates = [cv2.boundingRect(c) for c in cv2.findContours(motion, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
                      if 400 < cv2.contourArea(c) < 7200]
        self.hits = self.hits+1 if candidates else 0
        if self.hits < 3:
            return []
        x,y,w,h = max(candidates,key=lambda b:b[2]*b[3])
        return [(x,y,x+w,y+h)]


def update_file(path, lines):
    temp = path.with_suffix(".tmp")
    temp.write_text("\n".join(lines)+"\n", encoding="utf-8")
    temp.replace(path)


def worker(ch, exchange, archive, archive_lock):
    detector = None
    eye, cracks, slope = DriverEyes() if ch==1 else None, RoadSurface() if ch==3 else None, SlopeMotion() if ch==2 else None
    lane = VideoLaneAnalyzer() if ch==0 else None
    monitor = VehicleMonitor(.9, 10.) if ch==0 else None
    hazard = None
    if ch in HAZARD_SETTINGS:
        model_file,size,classes,threshold,interval,reasons = HAZARD_SETTINGS[ch]
        try:
            if ch==3:
                model = CorroboratedCracks(HazardModel(ROOT/"models"/model_file,size,classes,
                                      (*CorroboratedCracks.low,threshold[3])))
            else:
                model = HazardModel(ROOT/"models"/model_file,size,classes,threshold)
            hazard = LatestHazards(PersistentHazards(model,interval,range(len(reasons))),cpu=4 if ch==2 else 5)
        except Exception as exc:
            print(f"{CAMERAS[ch]} hazard model unavailable: {exc}",flush=True)
    seq = 0
    last_warning = {}
    pedestrian_hits = 0
    danger_events = 0
    while not stop.is_set():
        stamp = time.monotonic()
        seq, frame = exchange.frame(ch, seq)
        if frame is None:
            stop.wait(.025)
            continue
        overlays, rows, warnings = [], [], []
        lane_summary = ""
        stats = ""
        status = ("前向感知", "闭眼监测", "行人 / 土石扰动规则", "路面纹理规则")[ch]
        try:
            if ch in (0, 2):
                if detector is None:
                    detector = NativeObjectDetector(FIRST/"rk_yolo_srv", FIRST/"yolov8n.rknn", 0,
                                                    classes=CLASSES if ch==0 else {0:"person"})
                detections = filter_vehicle_duplicates(detector.detect(frame))
                if ch == 0:
                    vehicles = sum(det.label in VEHICLE_LABELS for det in detections)
                    obstacles = sum(det.label == "cone" for det in detections)
                    pedestrians = sum(det.label == "person" for det in detections)
                risks = monitor.update(detections, W, stamp, measured=True) if monitor else {}
                pedestrian_hits = pedestrian_hits+1 if any(d.label=="person" and d.score>=.45 for d in detections) else 0
                for i, det in enumerate(detections[:12]):
                    x1,y1,x2,y2 = det.box
                    risk = risks.get(i)
                    name = signal_color(frame, det.box) if det.label=="light" else LABEL.get(det.label, det.label)
                    distance = risk.distance_m if risk else None
                    if det.label=="person":
                        distance = .9 * W * 1.7 / (y2-y1) if y2-y1>=12 and y1>0 and y2<H-1 else None
                    in_path = .30 < ((x1+x2)*.5/W) < .70
                    severity = 2 if risk and risk.level=="high" else 0
                    reason = risk.reason if severity else ""
                    if det.label=="person" and det.score>=.45 and pedestrian_hits>=2 and (
                        (distance is not None and distance<12 and in_path) or ch==2):
                        severity, reason = 3, "行人优先"
                    if name=="红灯" and in_path:
                        severity, reason = 1, "前方红灯"
                    if det.label=="cone" and in_path and y2>H*.68:
                        severity, reason = 1, "疑似障碍物"
                    label = f"{name} {distance:.1f}m" if distance is not None else f"{name} {det.score:.0%}"
                    overlays.append((det.box, 0xff6b65 if severity else 0x65ddbf, label))
                    rows.append(f"O {x1} {y1} {x2} {y2} {distance if distance is not None else -1:.2f} {severity} {round(det.score*100)} {name}")
                    if severity:
                        warnings.append((severity, det.box, reason, det.score, distance))
            if lane:
                result = lane.analyze(frame,stamp)
                sides = int(result.left is not None)+2*int(result.right is not None)
                lane_summary = f"L {sides} {int(result.held)} {int(result.source=='guide')}"
                for line in (result.left, result.right):
                    lane_summary += " " + " ".join(map(str,line or (0,0,0,0)))
            if eye:
                regions, status = eye(frame, stamp)
                warnings.extend((1, b, "疑似持续闭眼", None, None) for b in regions)
            if hazard:
                status = "行人 / 滑坡视觉模型" if ch==2 else "RDD2022 路面裂缝模型"
                try:
                    hits = hazard.update(frame,stamp,lambda: exchange.detail_frame(ch))
                    warnings.extend((1,x.box,reasons[x.kind],x.score,None) for x in hits)
                except Exception as exc:
                    print(f"{CAMERAS[ch]} hazard inference unavailable: {exc}",flush=True)
                    status = "视觉模型异常 · 使用候选规则"
                    hazard.close()
                    hazard = None
            elif slope:
                warnings.extend((1, b, "疑似土石扰动", None, None) for b in slope(frame))
            elif cracks:
                warnings.extend((1, b, "疑似道路裂缝", None, None) for b in cracks(frame))
            new_warnings = dict(last_warning)
            for _, box, reason, score, distance in warnings:
                if len(overlays)<12 and all(overlay[0]!=box for overlay in overlays):
                    overlays.append((box, 0xffa365, reason))
                    confidence = -1 if score is None else round(score*100)
                    rows.append("O {} {} {} {} -1 1 {} {}".format(*box,confidence,reason))
                if stamp-new_warnings.get(reason, -999)>1.5:
                    risk = SimpleNamespace(reason=reason, distance_m=distance)
                    detection = SimpleNamespace(box=box, score=score)
                    with archive_lock:
                        saved = archive.save(CAMERAS[ch], frame, detection, risk)
                    if ch == 0 and saved:
                        danger_events += 1
                new_warnings[reason] = stamp
            last_warning = new_warnings
            if ch == 0:
                stats = f"C {vehicles} {danger_events} {obstacles} {pedestrians}"
        except (OSError, RuntimeError, cv2.error, ValueError) as exc:
            if detector is not None:
                detector.close()
                detector = None
            print(f"{PORTS[ch]}: {exc}", flush=True)
            status = "处理异常"
            stop.wait(.6)
        exchange.publish(ch, overlays[:12], "")
        top = max(warnings, key=lambda r:r[0], default=None)
        detail = f" · {top[4]:.1f}米" if top and top[4] is not None else ""
        update_file(RUN/f"view{ch}", [f"T {time.monotonic():.3f}", f"S {status}",
                    f"A {top[0]} {DIRECTIONS[ch]} · {top[2]}{detail}" if top else "A 0",
                    lane_summary, stats, *rows])
        stop.wait(max(0, .1 - (time.monotonic()-stamp)))
    if detector:
        detector.close()
    if hazard:
        hazard.close()


def main():
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    cv2.setNumThreads(1)
    exchange = Exchange(hazard_detail=True)
    archive = AlertArchive(ROOT/"alerts")
    archive_lock = threading.Lock()
    record_frames=RecordingFrames(RUN)
    threads = [threading.Thread(target=worker, args=(ch, exchange, archive, archive_lock),
                                name=f"camera-{port}") for ch, port in enumerate(PORTS)]
    threads.append(threading.Thread(target=record_loop, args=(RUN,record_frames.snapshot,stop), name="tf-recorder"))
    threads.append(threading.Thread(target=playback_loop, args=(RUN,stop), name="media-review"))
    for thread in threads:
        thread.start()
    try:
        while not stop.wait(.5):
            if not all(thread.is_alive() for thread in threads):
                raise RuntimeError("cockpit worker stopped")
    finally:
        stop.set()
        for thread in threads:
            thread.join()


if __name__ == "__main__":
    main()
