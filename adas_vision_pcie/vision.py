"""Vision algorithms and RKNN Model Zoo YOLOv8 adapter."""
from dataclasses import dataclass
from pathlib import Path
import struct
import subprocess

import cv2
import numpy as np


@dataclass
class Detection:
    box: tuple[int, int, int, int]
    score: float
    label: str


@dataclass
class Risk:
    index: int
    distance_m: float
    level: str


class DemoDetector:
    def detect(self, frame, frame_no=0):
        return [Detection((415, 275, 550, 370), .94, "car"),
                Detection((650, 295, 755, 366), .88, "bus"),
                Detection((155, 330, 230, 395), .82, "motorbike")]

    def close(self):
        pass


class NoModelDetector:
    def detect(self, frame, frame_no=0):
        return []

    def close(self):
        pass


class PCYOLODetector:
    """Ultralytics PyTorch detector for PC video validation."""
    VEHICLE_CLASSES = {1: "bike", 2: "car", 3: "motorbike", 5: "bus", 7: "truck"}

    def __init__(self, model_path="yolov8n.pt"):
        from ultralytics import YOLO
        self.model = YOLO(str(model_path))

    def detect(self, frame, frame_no=0):
        # Lower candidate threshold; Tracker confirms new boxes at 0.35.
        result = self.model.predict(frame, imgsz=640, conf=.25, verbose=False)[0]
        detections = []
        for box in result.boxes:
            cls = int(box.cls.item())
            if cls not in self.VEHICLE_CLASSES:
                continue
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            detections.append(Detection((x1, y1, x2, y2), float(box.conf.item()),
                                        self.VEHICLE_CLASSES[cls]))
        return detections

    def close(self):
        self.model = None


def detect_lanes(frame):
    """Classical lane overlay; experimental on real road footage."""
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 60, 150)
    mask = np.zeros_like(edges)
    polygon = np.array([[(int(.12*w), h), (int(.43*w), int(.43*h)),
                         (int(.57*w), int(.43*h)), (int(.88*w), h)]], np.int32)
    cv2.fillPoly(mask, polygon, 255)
    lines = cv2.HoughLinesP(cv2.bitwise_and(edges, mask), 1, np.pi/180, 45,
                            minLineLength=45, maxLineGap=35)
    if lines is None:
        return []
    groups = {"left": [], "right": []}
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        if x2 == x1:
            continue
        slope = (y2-y1)/(x2-x1)
        if -.9 < slope < -.3 and max(x1, x2) < .62*w:
            groups["left"].append((slope, x1, y1))
        elif .3 < slope < .9 and min(x1, x2) > .38*w:
            groups["right"].append((slope, x1, y1))
    result = []
    for group in groups.values():
        if not group:
            continue
        slopes = np.array([v[0] for v in group])
        intercepts = np.array([v[2]-v[0]*v[1] for v in group])
        m, b = float(np.median(slopes)), float(np.median(intercepts))
        y1, y2 = h-1, int(.48*h)
        x1, x2 = int((y1-b)/m), int((y2-b)/m)
        result.append((int(np.clip(x1, 0, w-1)), y1, int(np.clip(x2, 0, w-1)), y2))
    return result


def estimate_risks(detections, focal_px, vehicle_width_m, speed_kmh):
    """Pinhole width heuristic. Speed is a user assumption, not measured relative speed."""
    if focal_px <= 0 or vehicle_width_m <= 0 or speed_kmh < 0:
        raise ValueError("invalid calibration")
    result = []
    for i, det in enumerate(detections):
        width_px = max(1, det.box[2] - det.box[0])
        d = focal_px * vehicle_width_m / width_px
        ttc = d / max(speed_kmh / 3.6, .01)
        level = "高" if ttc < 2 else "中" if ttc < 4 else "低"
        result.append(Risk(i, d, level))
    return result


class RKNNDetector:
    """Decodes the nine-output optimized YOLOv8n/s/m in RKNN Model Zoo."""
    VEHICLE_CLASSES = {1: "bike", 2: "car", 3: "motorbike", 5: "bus", 7: "truck"}

    def __init__(self, model_path):
        from rknnlite.api import RKNNLite
        self.rknn = RKNNLite()
        if self.rknn.load_rknn(str(model_path)) != 0:
            raise RuntimeError("load_rknn failed")
        if self.rknn.init_runtime() != 0:
            self.rknn.release()
            raise RuntimeError("init_runtime failed")

    def close(self):
        self.rknn.release()

    def detect(self, frame, frame_no=0):
        h, w = frame.shape[:2]
        scale = min(640/w, 640/h)
        nw, nh = round(w*scale), round(h*scale)
        left, top = (640-nw)//2, (640-nh)//2
        # Match RKNN Model Zoo YOLOv8's black letterbox padding.
        image = np.zeros((640, 640, 3), np.uint8)
        image[top:top+nh, left:left+nw] = cv2.resize(frame, (nw, nh))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        outs = self.rknn.inference(inputs=[image])
        if outs is None or len(outs) != 9:
            raise RuntimeError("expected nine Model Zoo YOLOv8 outputs")
        boxes, scores, classes = [], [], []
        for branch in range(3):
            reg = np.asarray(outs[branch*3], dtype=np.float32)
            cls = np.asarray(outs[branch*3+1], dtype=np.float32)
            if reg.ndim != 4 or cls.ndim != 4 or reg.shape[1] != 64 or cls.shape[1] != 80:
                raise RuntimeError("unsupported YOLOv8 output layout")
            _, _, gh, gw = reg.shape
            reg = reg.reshape(1, 4, 16, gh, gw)
            reg -= reg.max(axis=2, keepdims=True)
            prob = np.exp(reg)
            prob /= prob.sum(axis=2, keepdims=True)
            distance = (prob * np.arange(16, dtype=np.float32)[None,None,:,None,None]).sum(axis=2)[0]
            yy, xx = np.meshgrid(np.arange(gh), np.arange(gw), indexing="ij")
            stride = 640/gh
            cx, cy = (xx+.5)*stride, (yy+.5)*stride
            score = cls[0].max(axis=0)
            class_id = cls[0].argmax(axis=0)
            valid = (score >= .25) & np.isin(class_id, list(self.VEHICLE_CLASSES))
            for y, x in zip(*np.where(valid)):
                l, t, r, b = distance[:, y, x]*stride
                x1 = np.clip(((cx[y,x]-l)-left)/scale, 0, w-1)
                y1 = np.clip(((cy[y,x]-t)-top)/scale, 0, h-1)
                x2 = np.clip(((cx[y,x]+r)-left)/scale, 0, w-1)
                y2 = np.clip(((cy[y,x]+b)-top)/scale, 0, h-1)
                boxes.append((int(x1), int(y1), int(x2), int(y2)))
                scores.append(float(score[y,x]))
                classes.append(int(class_id[y,x]))
        if not boxes:
            return []
        keep = cv2.dnn.NMSBoxes([list((a,b,c-a,d-b)) for a,b,c,d in boxes], scores, .25, .45)
        return [Detection(boxes[int(i)], scores[int(i)], self.VEHICLE_CLASSES[classes[int(i)]])
                for i in np.asarray(keep).reshape(-1)]


class NativeObjectDetector:
    """One private connection to the FPGA project's rk_yolo_srv helper."""

    def __init__(self, helper, model, core_mask, *, classes):
        self.classes = classes
        self.inference_ms = None
        self.process = subprocess.Popen(
            [str(Path(helper).resolve()), str(Path(model).resolve()), str(core_mask)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.sequence = 0
        ready = self.process.stdout.readline().split()
        if ready[:3] != [b"ready", b"640", b"640"]:
            self.close()
            raise RuntimeError("RKNN 检测模型启动失败")

    def detect(self, frame):
        height, width = frame.shape[:2]
        scale = min(640 / width, 640 / height)
        nw, nh = round(width * scale), round(height * scale)
        x0, y0 = (640 - nw) // 2, (640 - nh) // 2
        rgb = np.zeros((640, 640, 3), dtype=np.uint8)
        rgb[y0:y0 + nh, x0:x0 + nw] = cv2.cvtColor(
            cv2.resize(frame, (nw, nh)), cv2.COLOR_BGR2RGB)
        self.sequence = (self.sequence + 1) & 0x7fffffff
        self.process.stdin.write(struct.pack("<I", self.sequence))
        self.process.stdin.write(memoryview(rgb).cast("B"))
        self.process.stdin.flush()
        result = self.process.stdout.readline().split()
        if len(result) < 4 or int(result[0]) != self.sequence or float(result[1]) < 0:
            raise RuntimeError("RKNN 目标推理失败")
        self.inference_ms = float(result[1])
        count = int(result[3])
        values = result[4:]
        if count < 0 or len(values) != count * 6:
            raise RuntimeError("RKNN 目标结果格式异常")
        detections = []
        for offset in range(0, len(values), 6):
            x1, y1, x2, y2, score, class_id = values[offset:offset + 6]
            label = self.classes.get(int(class_id))
            if label is None or float(score) < .25:
                continue
            left = int(np.clip((float(x1) - x0) / scale, 0, width - 1))
            top = int(np.clip((float(y1) - y0) / scale, 0, height - 1))
            right = int(np.clip((float(x2) - x0) / scale, 0, width - 1))
            bottom = int(np.clip((float(y2) - y0) / scale, 0, height - 1))
            if right > left and bottom > top:
                detections.append(Detection((left, top, right, bottom), float(score), label))
        return detections

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        finally:
            self.process.stdout.close()
