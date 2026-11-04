"""Dual-channel FPGA and recording review console for RK3576."""
import argparse
from collections import deque
from dataclasses import dataclass
import json
from math import ceil, isfinite
from pathlib import Path
from queue import Empty, Full, Queue
import sqlite3
import sys
from threading import Event, Thread
import time

import cv2
import numpy as np

from alert_server import AlertRelay, DangerSnapshots
from fpga_capture import FpgaCapture
from green_lane import GreenLaneMonitor
from histogram import render_histogram
from lane import LaneAnalyzer
from sparse_tracking import DetectionCadence
from vehicle_risk import CAUTION, HIGH, NORMAL, UNKNOWN, RESULT_MAX_AGE, VehicleMonitor, filter_vehicle_duplicates
from vision import NativeObjectDetector, RKNNDetector
from weather import enhance

try:
    import arm_isp
except ModuleNotFoundError as exc:
    if exc.name != "arm_isp":
        raise
    host = Path(__file__).resolve().parent.parent / "isp_imx415_v0635b/prj/isp_imx415/host"
    sys.path.append(str(host))
    import arm_isp


BG, CARD, EDGE = "#f1f3f6", "#ffffff", "#cbd2dc"
INK, MUTED, ACCENT = "#111827", "#475569", "#fece14"
SUCCESS, AMBER = "#166534", "#92400e"
DANGER = "#b91c1c"
SOFT, FOCUS = "#e8ecf2", "#1d4ed8"
MAIN_TREND, AUX_TREND = "#925900", "#1d4ed8"
TREND_SECONDS = 20
WEATHER_MODES = ("关闭", "雾霾", "沙尘暴")
TARGET_CLASSES = (RKNNDetector.VEHICLE_CLASSES, {0: "person"})
SCREEN_KEYS = ("main", "aux")
ISP_SLIDERS = (("ccm_strength", "色彩矩阵强度"), ("wb_r", "白平衡红增益"),
               ("wb_b", "白平衡蓝增益"), ("gamma", "伽马"), ("contrast", "对比度"),
               ("brightness", "亮度"), ("denoise", "降噪"), ("sharpen", "锐化"),
               ("sharpen_sigma", "锐化半径"))
VEHICLE_BOX = {HIGH: (56, 53, 225), CAUTION: (40, 180, 255),
               NORMAL: (94, 197, 34), UNKNOWN: (157, 155, 148)}
VEHICLE_GLYPH = {HIGH: ("#f87171", "#b91c1c"), CAUTION: ("#fbbf24", "#b45309"), NORMAL: ("#4ade80", "#166534"),
                 UNKNOWN: ("#94a3b8", "#475569")}


def green_lane_status(lines):
    return ("双侧" if all(lines) else "仅左侧" if lines[0] is not None
            else "仅右侧" if lines[1] is not None else "未检出")


def speed_tag(risk):
    if risk.speed_kmh is not None:
        return f"~{risk.speed_kmh:.0f}km/h"
    if risk.closing_kmh is not None:
        return f"{risk.closing_kmh:+.0f}km/h"
    return "--"


def speed_summary(risk):
    speed = risk.closing_kmh
    if speed is None:
        return "相对速度待确认"
    if abs(speed) < .5:
        return "相对速度 ≈0 km/h"
    return f"{'接近' if speed > 0 else '远离'} ≈{abs(speed):.0f} km/h"


def draw_detection_boxes(output, detections, risks, measured, box_width):
    h, w = output.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = .38 if w <= 500 else .44
    labels = []
    priorities = {HIGH: 0, CAUTION: 1, NORMAL: 2, UNKNOWN: 3}
    for i, det in enumerate(detections):
        left, top, right, bottom = det.box
        risk = risks.get(i)
        if risk is None:
            text = f"{det.label} {det.score:.0%}" if measured else f"{det.label} TRK"
            color, order, distance = (255, 214, 125), 2, 0
        else:
            distance = risk.distance_m if risk.distance_m is not None else float("inf")
            text = f"~{distance:.0f}m {speed_tag(risk)}" if risk.distance_m is not None else f"{det.label} --"
            color, order = VEHICLE_BOX[risk.level], priorities[risk.level]
        cv2.rectangle(output, (left, top), (right, bottom), color, box_width)
        labels.append((order, distance, det.box, color, text))

    occupied = []
    for order, _, (left, top, right, bottom), color, text in sorted(labels, key=lambda item: item[:2]):
        (tw, th), baseline = cv2.getTextSize(text, font, scale, 1)
        tag_w, tag_h = min(w, tw + 8), th + baseline + 4
        positions = [(left, top - tag_h), (right - tag_w, top - tag_h),
                     (left, top - 2*tag_h), (right - tag_w, top - 2*tag_h),
                     (left, bottom + 1), (right - tag_w, bottom + 1)]
        for x, y in positions:
            x, y = max(0, min(x, w - tag_w)), max(0, min(y, h - tag_h))
            if not any(x < r + 2 and x + tag_w + 2 > l and y < b + 2 and y + tag_h + 2 > t
                       for l, t, r, b in occupied):
                break
        else:
            if order > 1:
                continue
            x, y = max(0, min(left, w - tag_w)), max(0, min(top - tag_h, h - tag_h))
        occupied.append((x, y, x + tag_w, y + tag_h))
        cv2.rectangle(output, (x, y), (x + tag_w - 1, y + tag_h - 1), color, -1)
        cv2.putText(output, text, (x + 4, y + th + 2), font, scale,
                    (255, 255, 255) if order == 0 else (17, 24, 39), 1, cv2.LINE_AA)


def screen_corners(values):
    corners = np.asarray(values, np.float32).reshape(4, 2)
    if (not np.all((0 <= corners) & (corners <= 1)) or
            not cv2.isContourConvex(corners) or cv2.contourArea(corners, oriented=True) < .01):
        raise ValueError("请按左上、右上、右下、左下的顺序选取屏幕内角")
    return tuple(float(value) for value in corners.ravel())


def read_screens(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [screen_corners(data[key]) if data.get(key) is not None else None for key in SCREEN_KEYS]
    except FileNotFoundError:
        return [None, None]
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(f"Screen calibration ignored: {exc}", file=sys.stderr, flush=True)
        return [None, None]


def preprocess(frame, settings):
    mode, dehaze, multiscale, _ = settings
    enhanced = enhance(frame, mode=mode, strength=dehaze) if mode != "关闭" and dehaze else frame
    output = enhanced
    if multiscale:
        fine = cv2.GaussianBlur(output, (5, 5), 0)
        output = cv2.addWeighted(output, 1.24, fine, -.24, 0)
    return enhanced, output


def draw_lanes(output, lane, analysis_frame):
    result = lane.analyze(analysis_frame)
    both = bool(result.left and result.right)
    if both and (result.offset_fraction is None or result.left[2] >= result.right[2]):
        return output, "未识别", 0.
    lines = [line for line in (result.left, result.right) if line is not None]
    if not lines:
        return output, "未识别", 0.
    output = output.copy()
    confirmed = both and not result.held
    color = (120, 228, 70) if confirmed else (88, 190, 255)
    if confirmed:
        band = np.int32([lines[0][:2], lines[0][2:], lines[1][2:], lines[1][:2]])
        overlay = output.copy()
        cv2.fillConvexPoly(overlay, band, color)
        cv2.addWeighted(overlay, .13, output, .87, 0, dst=output)
    for line in lines:
        if confirmed:
            cv2.line(output, line[:2], line[2:], color, 2, cv2.LINE_AA)
        else:
            x1, y1, x2, y2 = line
            for i in range(0, 10, 2):
                a, b = i / 10, (i + 1) / 10
                cv2.line(output, (round(x1 + a * (x2-x1)), round(y1 + a * (y2-y1))),
                         (round(x1 + b * (x2-x1)), round(y1 + b * (y2-y1))), color, 2, cv2.LINE_AA)
    status = "短时估计" if result.held else "双侧边界" if both else "单侧边界"
    return output, status, result.confidence


@dataclass
class PreparedFrame:
    original: np.ndarray
    enhanced: np.ndarray
    preview: np.ndarray
    settings: tuple[str, int, bool, bool]
    timestamp: float | None
    started: float
    work_seconds: float


def publish_latest(queue, item):
    try:
        queue.put_nowait(item)
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
        queue.put_nowait(item)


class Channel:
    def __init__(self, source, width, *, index=0, flip_vertical=False, screen=None,
                 screen_only=False, detector_backend=None, detect_every=None,
                 rear_view=False, focal_ratio=.9, near_m=10., isp=None, alert_relay=None):
        self.source = source
        self.width = width
        self.index = index
        self.rear_view = rear_view
        self.vehicle_monitor = (VehicleMonitor(focal_ratio, near_m, rear_view=rear_view)
                                if index == 0 or rear_view else None)
        self.ego_kmh = None
        self.alert_relay = alert_relay
        self.isp = isp
        self.min_score = .30
        self.box_width = 2
        self.flip_vertical = flip_vertical
        self.screen = screen
        self.screen_pending = screen_only and screen is None
        self.calibration_frame = None
        self.screen_map = None
        self.detector_backend = detector_backend
        self.detect_every = detect_every if detect_every is not None else (3, 2)[index]
        self.settings = ("雾霾", 45, True, False)
        self.stop = Event()
        self.latest = Queue(maxsize=1)
        self.inference_history = deque(maxlen=600)
        self.thread = Thread(target=self.run)
        self.thread.start()

    def publish(self, item):
        publish_latest(self.latest, item)

    def select_detections(self, detections):
        accepted = [det for det in detections if det.score >= self.min_score]
        return filter_vehicle_duplicates(accepted) if self.vehicle_monitor is not None else accepted

    def prepare(self, capture, live):
        started = time.perf_counter()
        ok, frame = capture.read()
        if not ok:
            message = getattr(capture, "error", "") if live else "录播结束"
            return message or "信号中断"
        if live:
            timestamp = capture.timestamp_ms
        else:
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC)
            if not isfinite(timestamp) or timestamp <= 0:
                fps = capture.get(cv2.CAP_PROP_FPS)
                timestamp = (1000 * max(0, capture.get(cv2.CAP_PROP_POS_FRAMES) - 1) / fps
                             if 1 <= fps <= 240 else None)
        processing = time.perf_counter()
        height, width = frame.shape[:2]
        if self.flip_vertical:
            frame = cv2.flip(frame, 0)
        if live:
            self.calibration_frame = (time.monotonic(), frame)
        if self.screen is not None:
            if self.screen_map is None or self.screen_map[0] != (width, height):
                source = np.array(self.screen, np.float32).reshape(4, 2) * np.float32([width - 1, height - 1])
                center = source.mean(axis=0)
                source = center + .99 * (source - center)
                target_width = min(width, self.width)
                target_height = round(target_width * 9 / 16)
                corners = np.float32([(0, 0), (target_width - 1, 0),
                                      (target_width - 1, target_height - 1), (0, target_height - 1)])
                transform = cv2.getPerspectiveTransform(source, corners)
                self.screen_map = ((width, height), transform, (target_width, target_height))
            _, transform, size = self.screen_map
            frame = cv2.warpPerspective(frame, transform, size)
        elif width > self.width:
            frame = cv2.resize(frame, (self.width, max(1, round(height * self.width / width))),
                               interpolation=cv2.INTER_AREA)
        settings = self.settings
        corrected = frame
        if self.isp is not None and not self.screen_pending:
            params = self.isp.get()
            corrected = arm_isp.apply(frame, params)
            if params["enable"]:
                mode, strength, _, lanes = settings
                settings = (mode, strength, False, lanes)
        enhanced, preview = (preprocess(corrected, settings) if self.index == 0 and not self.screen_pending
                             else (corrected, corrected))
        return PreparedFrame(frame, enhanced, preview, settings, timestamp, started,
                             time.perf_counter() - processing)

    def prefetch(self, capture, queue):
        try:
            while not self.stop.is_set():
                item = self.prepare(capture, True)
                publish_latest(queue, item)
                if isinstance(item, str):
                    return
        except (OSError, ValueError, cv2.error) as exc:
            publish_latest(queue, str(exc))

    def run(self):
        capture = None
        reader = None
        detector = None
        target_status = "待标定" if self.screen_pending else "未启用"
        detection_source = "—"
        try:
            live = self.source.startswith(("http://", "https://"))
            snapshots = (DangerSnapshots(self.alert_relay, self.index + 1, live)
                         if self.alert_relay is not None and self.vehicle_monitor is not None else None)
            reduction = 1
            if self.index == 0 and self.width <= 960:
                reduction = 4 if self.width <= 480 and self.screen is None else 2
            capture = (FpgaCapture(self.source, jpeg_reduction=reduction)
                       if live else cv2.VideoCapture(self.source))
            if not capture.isOpened():
                self.publish((None, None, getattr(capture, "error", "") or "无法打开视频", None))
                return
            if self.detector_backend is not None and not self.screen_pending:
                try:
                    classes = TARGET_CLASSES[self.index]
                    if self.rear_view:
                        classes = {**classes, **TARGET_CLASSES[0]}
                    detector = NativeObjectDetector(*self.detector_backend, classes=classes)
                except (OSError, RuntimeError, ValueError) as exc:
                    print(f"{self.source}: {exc}", file=sys.stderr, flush=True)
                    target_status = "模型异常"
            fps = capture.get(cv2.CAP_PROP_FPS)
            period = 1 / fps if 1 <= fps <= 240 else 1 / 25
            lane = LaneAnalyzer() if self.index == 0 and not live else None
            green_lane = GreenLaneMonitor() if self.index == 0 else None
            cadence = DetectionCadence(self.detect_every)
            if lane is not None:
                lane.local_contrast = True
                lane.hough_votes = 23
                lane.min_line_pct = 4
                lane.crop_to_roi = True
                lane.stable_fit = True
                lane.hold_frames = 2
            previous_settings = None
            completions = deque()
            if live and self.index == 0:
                prepared = Queue(maxsize=1)
                reader = Thread(target=self.prefetch, args=(capture, prepared))
                reader.start()
            while not self.stop.is_set():
                if reader is None:
                    item = self.prepare(capture, live)
                else:
                    try:
                        item = prepared.get(timeout=.2)
                    except Empty:
                        continue
                if isinstance(item, str):
                    self.publish((None, None, item, None))
                    return
                processing = time.perf_counter()
                frame, detection_frame, output = item.original, item.enhanced, item.preview
                status = "—"
                lane_support = "—"
                path = None
                green_lines = (None, None)
                capture_time = (item.timestamp / 1000 if item.timestamp is not None and isfinite(item.timestamp)
                                else item.started)
                if self.screen_pending:
                    status = "待标定" if self.index == 0 else "—"
                elif self.index == 0:
                    if item.settings != previous_settings:
                        if lane is not None:
                            lane.reset()
                        cadence.reset()
                        self.vehicle_monitor.reset()
                        previous_settings = item.settings
                    green_lines = green_lane.update(frame, capture_time)
                    if lane is None or any(green_lines):
                        status = green_lane_status(green_lines)
                    elif item.settings[3]:
                        output, status, support = draw_lanes(output, lane, detection_frame)
                        if status == "双侧边界":
                            left, right = lane.last_valid.left, lane.last_valid.right
                            width = frame.shape[1]
                            path = ((left[0] + right[0]) / (2 * width), (left[2] + right[2]) / (2 * width))
                        lane_support = f"{support:.0%}"
                    else:
                        status = "关闭"
                inference_ms = None
                objects = []
                vehicle_updated = None
                if detector is not None:
                    try:
                        detections, inference_ms = cadence.update(
                            detector, frame, detection_frame, item.started, select_boxes=self.select_detections)
                        detections = [det for det in detections if det.score >= self.min_score]
                        detection_source = "NPU" if inference_ms is not None else "光流" if detections else "间隔"
                        target_status = str(len(detections))
                        risks = {}
                        if self.vehicle_monitor is not None:
                            risks = self.vehicle_monitor.update(
                                detections, frame.shape[1], capture_time, measured=inference_ms is not None,
                                ego_kmh=self.ego_kmh)
                            objects = list(risks.values())
                            vehicle_updated = item.started
                        if detections:
                            if output is item.preview:
                                output = output.copy()
                            draw_detection_boxes(output, detections, risks, inference_ms is not None,
                                                 self.box_width)
                        if snapshots is not None and objects:
                            snapshots.observe(objects, output, item.started)
                    except (OSError, RuntimeError, ValueError) as exc:
                        print(f"{self.source}: {exc}", file=sys.stderr, flush=True)
                        target_status = "推理异常"
                        detection_source = "—"
                        objects, vehicle_updated = [], None
                        detector.close()
                        detector = None
                now = time.perf_counter()
                if inference_ms is not None:
                    self.inference_history.append((time.monotonic(), inference_ms))
                completions.append(now)
                while now - completions[0] > 1:
                    completions.popleft()
                span = now - completions[0]
                fps_label = f"{(len(completions) - 1) / span:.1f}" if span >= .35 else "—"
                work_ms = (item.work_seconds + now - processing) * 1000
                metrics = (f"{frame.shape[1]} × {frame.shape[0]}", fps_label,
                           f"{work_ms:.1f}",
                           "—" if inference_ms is None else f"{inference_ms:.1f}",
                           status, target_status, detection_source, lane_support, path, objects, item.preview,
                           vehicle_updated, green_lines, item.started)
                self.publish((frame, output, metrics, item.timestamp))
                if not live:
                    self.stop.wait(max(0, period - (time.perf_counter() - item.started)))
        except (OSError, ValueError, cv2.error) as exc:
            self.publish((None, None, str(exc), None))
        finally:
            if reader is not None:
                self.stop.set()
                reader.join()
            if capture is not None:
                capture.release()
            if detector is not None:
                detector.close()


class Console:
    def __init__(self, root, args):
        import tkinter as tk
        from tkinter import filedialog, font, ttk
        from PIL import Image, ImageTk

        self.tk, self.filedialog = tk, filedialog
        self.ttk = ttk
        self.Image, self.ImageTk = Image, ImageTk
        self.metric_font = font.nametofont("TkFixedFont").actual("family")
        self.root, self.args = root, args
        self.alert_relay = None
        if getattr(args, "alert_port", None):
            try:
                self.alert_relay = AlertRelay(args.alert_port, args.alert_db)
            except (OSError, ValueError, sqlite3.Error) as exc:
                print(f"PC alert relay unavailable: {exc}", file=sys.stderr, flush=True)
        self.channels = [None, None]
        self.screen_config = Path(getattr(args, "screen_config", "screen-roi.json"))
        self.screens = read_screens(self.screen_config)
        for index, name in enumerate(("main_screen", "aux_screen")):
            corners = getattr(args, name, None)
            if corners is not None:
                self.screens[index] = screen_corners(corners)
        self.screen_only = getattr(args, "screen_only", False)
        self.path = None
        self.green_lines = (None, None)
        self.green_lines_at = None
        self.objects = [[], []]
        self.vehicle_updated = [None, None]
        self.alert_style = None
        self.hist_inputs = [None, None]
        self.hist_source = tk.StringVar(value="主摄")
        self.isp_params = [arm_isp.Params(), arm_isp.Params()]
        self.detector_controls = [(0.30, 2), (0.30, 2)]
        self.tuning_window = None
        self.speed_window = None
        self.ego_kmh = getattr(args, "ego_kmh", None)
        for params in self.isp_params:
            params.set("enable", 0)
        self.frames = [None, None]
        self.rendered = [None, None]
        self.cards = []
        self.histories = [deque(maxlen=160), deque(maxlen=160)]
        self.charts = []
        self.detail_cells = []
        self.compact_monitor = False
        self.chart_refresh = 0.
        self.raw = tk.BooleanVar()
        self.rear_mode = tk.BooleanVar(value=getattr(args, "aux_rear", False))
        self.weather = tk.StringVar(value="雾霾")
        self.dehaze = tk.IntVar(value=45)
        self.multiscale = tk.BooleanVar(value=True)
        self.lanes = tk.BooleanVar(value=False)
        root.title("SENTRY / 双路视觉工作台")
        root.geometry("1280x730")
        root.minsize(780, 460)
        root.configure(bg=BG)
        self.style_controls()
        self.build()
        root.bind("<F11>", self.toggle_fullscreen)
        root.bind("<Escape>", lambda _: self.set_fullscreen(False))
        self.set_fullscreen(not getattr(args, "windowed", False))
        if args.fpga:
            self.open_fpga()
        else:
            for index, path in enumerate((args.video_a, args.video_b)):
                if path:
                    self.open(index, path)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    def set_fullscreen(self, enabled):
        self.fullscreen = enabled
        self.root.attributes("-fullscreen", enabled)
        self.fullscreen_button.configure(text="退出全屏" if enabled else "进入全屏")

    def toggle_fullscreen(self, event=None):
        self.set_fullscreen(not self.fullscreen)

    def label(self, parent, value, size=11, color=INK, bg=CARD, bold=False, mono=False, **kwargs):
        return self.tk.Label(parent, text=value, fg=color, bg=bg,
                             font=(self.metric_font if mono else "TkDefaultFont",
                                   size, "bold" if bold else "normal"),
                             **kwargs)

    def style_controls(self):
        style = self.ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Sentry.TButton", background=SOFT, foreground=INK, bordercolor=EDGE,
                        padding=(12, 8), borderwidth=1, relief="flat",
                        font=("TkDefaultFont", 11))
        style.map("Sentry.TButton", background=[("active", EDGE)], bordercolor=[("focus", FOCUS)])
        style.configure("Connect.TButton", background=ACCENT, foreground=INK,
                        padding=(16, 8), borderwidth=1, relief="flat",
                        font=("TkDefaultFont", 11, "bold"))
        style.map("Connect.TButton", background=[("active", "#f8bd0a")],
                  bordercolor=[("focus", FOCUS)])
        style.configure("Sentry.TCheckbutton", background=CARD, foreground=INK,
                        indicatorbackground=CARD, indicatormargin=5,
                        font=("TkDefaultFont", 11))
        style.map("Sentry.TCheckbutton", background=[("active", CARD)],
                  indicatorbackground=[("selected", ACCENT)])
        style.configure("Sentry.Horizontal.TScale", background=INK, troughcolor=EDGE,
                        borderwidth=1, sliderlength=14)

    def button(self, parent, label, action, *, primary=False):
        style = "Connect.TButton" if primary else "Sentry.TButton"
        return self.ttk.Button(parent, text=label, command=action, style=style, cursor="hand2")

    def check(self, parent, label, value):
        self.ttk.Checkbutton(parent, text=label, variable=value, style="Sentry.TCheckbutton"
                             ).pack(side="left", padx=6)

    def build(self):
        tk = self.tk
        header = tk.Frame(self.root, bg=CARD, highlightbackground=EDGE, highlightthickness=1)
        header.pack(fill="x")
        heading = tk.Frame(header, bg=CARD)
        heading.pack(fill="x", padx=24, pady=12)
        self.label(heading, "S", 19, INK, ACCENT, bold=True, mono=True,
                   padx=10, pady=5).pack(side="left", padx=(0, 12))
        brand = tk.Frame(heading, bg=CARD)
        brand.pack(side="left")
        self.label(brand, "SENTRY", 19, INK, bold=True).pack(anchor="w")
        self.label(brand, "安路赛题三  /  FPGA + RK3576", 10, MUTED).pack(anchor="w")
        self.button(heading, "关闭", self.close).pack(side="right")
        self.fullscreen_button = self.button(heading, "进入全屏", self.toggle_fullscreen)
        self.fullscreen_button.pack(side="right", padx=6)
        self.button(heading, "连接双路 FPGA", self.open_fpga, primary=True).pack(side="right")
        self.speed_button = self.button(heading, self.speed_button_text(), self.show_speed_settings)
        self.speed_button.pack(side="right", padx=6)

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(side="bottom", fill="x", padx=24, pady=(0, 8))
        self.label(footer, "MIPI CSI  /  FPGA 预处理与压缩  /  PCIe  /  RK3576",
                   10, MUTED, BG).pack(side="left")
        self.label(footer, "车框速度  + 接近 / − 远离", 10, MUTED, BG).pack(side="left", padx=14)
        self.label(footer, "F11  切换全屏     Esc  退出全屏",
                   10, MUTED, BG).pack(side="right")
        controls = tk.Frame(self.root, bg=CARD, highlightbackground=EDGE, highlightthickness=1)
        controls.pack(side="bottom", fill="x", padx=24, pady=(8, 8))
        self.label(controls, "主摄调节", 12, INK, bold=True).pack(side="left", padx=12, pady=9)
        self.label(controls, "天气增强", 10, MUTED).pack(side="left", padx=(0, 4))
        self.ttk.Combobox(controls, textvariable=self.weather, values=WEATHER_MODES,
                          state="readonly", width=7).pack(side="left", padx=(0, 8))
        self.label(controls, "强度", 10, MUTED).pack(side="left")
        self.ttk.Scale(controls, from_=0, to=100, orient="horizontal", variable=self.dehaze,
                       command=lambda value: self.dehaze.set(round(float(value))),
                       style="Sentry.Horizontal.TScale", length=82).pack(side="left", padx=4)
        tk.Label(controls, textvariable=self.dehaze, width=3, fg=INK, bg=CARD,
                 font=(self.metric_font, 11, "bold")).pack(side="left", padx=(0, 4))
        self.check(controls, "轻锐化", self.multiscale)
        self.recording_lanes = self.ttk.Checkbutton(controls, text="录播画车道线", variable=self.lanes,
                                                   style="Sentry.TCheckbutton")
        self.recording_lanes.pack(side="left", padx=6)
        self.recording_lanes.state(["disabled"])
        self.check(controls, "查看原图", self.raw)
        self.ttk.Checkbutton(controls, text="副摄后视", variable=self.rear_mode,
                             command=self.reopen_aux, style="Sentry.TCheckbutton").pack(side="left", padx=4)
        self.button(controls, "图像调参", self.show_tuning).pack(side="right", padx=8)

        grid = tk.Frame(self.root, bg=BG)
        grid.pack(fill="both", expand=True, padx=24, pady=(8, 0))
        grid.columnconfigure(0, minsize=340)
        grid.columnconfigure(1, weight=1)
        for index, title in enumerate(("主摄像头", "副摄像头")):
            grid.rowconfigure(index, weight=1, uniform="video")
            card = tk.Frame(grid, bg=CARD, highlightbackground=EDGE, highlightthickness=1)
            card.grid(row=index, column=0, sticky="nsew", padx=(0, 12),
                      pady=(0, 4) if index == 0 else (4, 0))
            bar = tk.Frame(card, bg=CARD)
            bar.pack(fill="x", padx=8, pady=(6, 2))
            self.label(bar, f"CH 0{index + 1}", 10, INK, ACCENT if index == 0 else SOFT,
                       mono=True, bold=True, padx=8, pady=4).pack(side="left", padx=(0, 8))
            self.label(bar, title, 13, INK, bold=True).pack(side="left")
            state = self.label(bar, "待机", 10, MUTED, SOFT, padx=8, pady=4)
            state.pack(side="left", padx=8)
            self.button(bar, "打开录播", lambda i=index: self.choose(i)).pack(side="right")
            source_bar = tk.Frame(card, bg=CARD)
            source_bar.pack(fill="x", padx=8, pady=(0, 4))
            source = self.label(source_bar, "选择录播或连接 FPGA", 10, MUTED, anchor="w", width=1)
            source.pack(side="left", fill="x", expand=True)
            self.ttk.Button(source_bar, text="标定屏幕", command=lambda i=index: self.calibrate_screen(i)
                            ).pack(side="right")
            canvas = tk.Canvas(card, bg=CARD, highlightthickness=0, width=1, height=1)
            canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            self.cards.append((source, canvas, state))
        self.build_monitor(grid)
        grid.bind("<Configure>", self.resize_monitor)

    def resize_monitor(self, event):
        # Match the video column to the height available for two stacked frames.
        ratios = (16 / 9, 960 / 528)
        widths = []
        for (_, canvas, _), ratio in zip(self.cards, ratios):
            chrome = canvas.master.winfo_reqheight() - canvas.winfo_reqheight()
            widths.append((event.height / 2 - 4 - chrome) * ratio)
        column_width = max(340, min(round(min(widths)) + 30, event.width - 310))
        event.widget.columnconfigure(0, minsize=column_width)
        compact = event.height < 460
        if compact == self.compact_monitor:
            return
        self.compact_monitor = compact
        self.chart_panel.rowconfigure(4, weight=0 if compact else 1)
        for cell in self.detail_cells:
            if compact:
                cell.grid_remove()
            else:
                cell.grid()

    def build_monitor(self, grid):
        tk = self.tk
        panel = tk.Frame(grid, bg=BG)
        self.chart_panel = panel
        panel.grid(row=0, column=1, rowspan=2, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        overview = tk.Frame(panel, bg=CARD, highlightbackground=EDGE, highlightthickness=1)
        overview.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        title = tk.Frame(overview, bg=CARD)
        title.pack(fill="x", padx=12, pady=(8, 4))
        self.label(title, "实时态势", 15, bold=True).pack(side="left")
        self.alert_panel = tk.Frame(title, bg=SOFT, highlightthickness=1, highlightbackground=EDGE)
        self.alert_panel.pack(side="right")
        self.alert_title = self.label(self.alert_panel, "实时安全预警", 11, bold=True, anchor="e")
        self.alert_title.pack(fill="x", padx=10, pady=(3, 0))
        self.alert_detail = self.label(self.alert_panel, "", 9, anchor="e", justify="right", height=2)
        self.alert_detail.pack(fill="x", padx=10, pady=(0, 4))
        stats = tk.Frame(overview, bg=CARD)
        stats.pack(fill="x", padx=8, pady=(0, 8))
        stats.columnconfigure(0, weight=1)
        self.metrics = [[], []]
        for column, (name, color) in enumerate((("CH 01 主摄", MAIN_TREND),
                                               ("CH 02 副摄", AUX_TREND)), start=1):
            stats.columnconfigure(column, weight=1, uniform="values")
            self.label(stats, name, 10, color, SOFT, bold=True, pady=4
                       ).grid(row=0, column=column, sticky="ew", padx=2)
        for row, name in enumerate(("处理分辨率", "处理帧率 · fps", "单帧处理 · ms",
                                    "RKNN 推理 · ms", "车道边界", "车辆 / 行人", "识别来源",
                                    "车道拟合支持度"), start=1):
            background = BG if row % 2 else CARD
            caption = self.label(stats, name, 10, MUTED, background, anchor="w", padx=8)
            caption.grid(row=row, column=0, sticky="nsew")
            cells = [caption]
            for index in range(2):
                value = self.label(stats, "—", 11, INK, background,
                                   bold=True, mono=row not in (5, 7))
                value.grid(row=row, column=index + 1, sticky="nsew")
                self.metrics[index].append(value)
                cells.append(value)
            if row in (1, 3, 8):
                self.detail_cells.extend(cells)

        panel.columnconfigure(0, weight=3, uniform="telemetry")
        panel.columnconfigure(1, weight=2, uniform="telemetry")
        path_card = tk.Frame(panel, bg=CARD, highlightbackground=EDGE, highlightthickness=1)
        path_card.grid(row=2, column=1, rowspan=3, sticky="nsew", padx=(8, 0))
        self.label(path_card, "3D 行车视图", 12, bold=True).pack(anchor="w", padx=10, pady=(8, 2))
        self.path_lanes = self.label(path_card, "主摄绿色标线 · 待识别", 9, MUTED)
        self.path_lanes.pack(anchor="w", padx=10)
        self.distance_status = self.label(path_card, "单目距离估算", 9, MUTED)
        self.distance_status.pack(anchor="w", padx=10)
        hist_bar = tk.Frame(path_card, bg=CARD)
        hist_bar.pack(side="bottom", fill="x", padx=8, pady=(4, 6))
        self.label(hist_bar, "RGB 直方图", 10, bold=True).pack(side="left")
        self.ttk.Combobox(hist_bar, textvariable=self.hist_source, values=("主摄", "副摄"),
                          state="readonly", width=5).pack(side="right")
        self.hist_canvas = tk.Canvas(path_card, width=1, height=72, bg=INK, highlightthickness=0)
        self.hist_canvas.pack(side="bottom", fill="x", padx=8)
        self.path_canvas = tk.Canvas(path_card, width=1, height=1, bg=INK, highlightthickness=0)
        self.path_canvas.pack(fill="both", expand=True, padx=8, pady=8)

        for row, (name, unit, step) in enumerate((("处理帧率", "fps", 5),
                                                  ("RKNN 推理耗时", "ms", 10),
                                                  ("识别目标数", "个", 1)), start=2):
            panel.rowconfigure(row, weight=1, uniform="trend")
            card = tk.Frame(panel, bg=CARD, highlightbackground=EDGE, highlightthickness=1)
            card.grid(row=row, column=0, sticky="nsew", pady=(0, 8) if row < 4 else 0)
            header = tk.Frame(card, bg=CARD)
            header.pack(fill="x", padx=12, pady=(6, 0))
            self.label(header, name, 12, bold=True).pack(side="left")
            self.label(header, "● 行人" if row == 4 else "● 副摄", 9, AUX_TREND).pack(side="right")
            self.label(header, "● 车辆" if row == 4 else "● 主摄", 9, MAIN_TREND).pack(side="right", padx=8)
            canvas = tk.Canvas(card, bg=CARD, width=1, height=1, highlightthickness=0)
            canvas.pack(fill="both", expand=True, padx=8, pady=(1, 4))
            self.charts.append((canvas, unit, step))
            if row == 4:
                self.detail_cells.append(card)

    def draw_charts(self, now):
        for index, (canvas, unit, step) in enumerate(self.charts):
            w, h = canvas.winfo_width(), canvas.winfo_height()
            canvas.delete("all")
            if w < 80 or h < 28:
                continue
            left, right = 38, w - 12
            top, bottom = (7, h - 13) if h < 60 else (12, h - 19)
            if index == 1:
                data = [[(stamp, value) for stamp, value in channel.inference_history.copy()
                         if now - stamp <= TREND_SECONDS] if channel is not None else []
                        for channel in self.channels]
            else:
                value_index = 0 if index == 0 else 1
                data = [[(stamp, values[value_index]) for stamp, values in history
                         if now - stamp <= TREND_SECONDS and values[value_index] is not None]
                        for history in self.histories]
            peak = max((value for samples in data for _, value in samples), default=0)
            high = max(step, ceil(peak / step) * step)
            ticks = (0, 1) if h < 60 or (unit == "个" and high % 2) else (0, .5, 1)
            for fraction in ticks:
                y = bottom - fraction * (bottom - top)
                canvas.create_line(left, y, right, y, fill=SOFT)
                canvas.create_text(left - 5, y, anchor="e", text=f"{high * fraction:g}",
                                   fill=MUTED, font=(self.metric_font, 9))
            canvas.create_text(left, h - 1, anchor="sw", text=f"−{TREND_SECONDS} s",
                               fill=MUTED, font=(self.metric_font, 9))
            canvas.create_text(right, h - 1, anchor="se", text=f"现在 · {unit}",
                               fill=MUTED, font=("TkDefaultFont", 9))
            if not any(data):
                canvas.create_text((left + right) / 2, (top + bottom) / 2, text="等待数据",
                                   fill=MUTED, font=("TkDefaultFont", 10))
            for samples, color in zip(data, (MAIN_TREND, AUX_TREND)):
                points = []
                last_time = None
                smoothed = None
                for stamp, value in samples:
                    if index == 1:
                        smoothed = (value if last_time is None or stamp - last_time > 1.5
                                    else .78 * smoothed + .22 * value)
                        value = smoothed
                    x = right - (now - stamp) / TREND_SECONDS * (right - left)
                    y = bottom - value / high * (bottom - top)
                    if last_time is not None and stamp - last_time > 1.5:
                        if len(points) >= 4:
                            canvas.create_line(*points, fill=color, width=2)
                        points = []
                    if index == 2 and points:
                        points.extend((x, points[-1]))
                    points.extend((x, y))
                    last_time = stamp
                if index == 1 and points and now - last_time <= 1.5:
                    canvas.create_line(points[-2], points[-1], right, points[-1],
                                       fill=color, dash=(3, 3), width=2)
                if len(points) >= 4:
                    canvas.create_line(*points, fill=color, width=2)
                if points:
                    x, y = points[-2:]
                    canvas.create_oval(x-3, y-3, x+3, y+3, fill=color, outline="")

    def fresh_vehicles(self, now):
        inputs = 2 if self.rear_mode.get() else 1
        return [self.objects[i] if updated is not None and now - updated <= RESULT_MAX_AGE else None
                for i, updated in enumerate(self.vehicle_updated[:inputs])]

    def draw_safety(self, vehicles):
        names = ("前方", "后方")
        all_targets = [(i, target) for i, targets in enumerate(vehicles) for target in targets or ()]
        def priority(item):
            target = item[1]
            return (target.ttc_s if target.ttc_s is not None else float("inf"), target.distance_m)
        warning = min(((i, t) for i, t in all_targets if t.level in (HIGH, CAUTION)),
                      key=lambda item: (item[1].level != HIGH, priority(item)), default=None)
        nearest = min(((i, t) for i, t in all_targets if t.distance_m is not None),
                      key=lambda item: item[1].distance_m, default=None)
        if warning is not None:
            index, target = warning
            title = "高风险" if target.level == HIGH else "注意"
            detail = f"{names[index]} ≈{target.distance_m:.1f} m · {target.reason}\n{speed_summary(target)}"
            if target.ttc_s is not None:
                detail += f" · TTC {target.ttc_s:.1f} s"
            fg, bg, border = ((DANGER, "#fef2f2", "#fca5a5") if target.level == HIGH
                              else (AMBER, "#fffbeb", "#fcd34d"))
        elif all(feed is None for feed in vehicles):
            main = self.channels[0]
            title = "等待监测"
            detail = ("请先标定主摄屏幕" if main is not None and main.screen_pending
                      else "暂无有效车辆检测数据")
            fg, bg, border = MUTED, SOFT, EDGE
        elif any(feed is None for feed in vehicles):
            title, detail = "部分通道不可用", "请检查前后视信号"
            fg, bg, border = AMBER, "#fffbeb", "#fcd34d"
        elif any(t.level == UNKNOWN for _, t in all_targets):
            title, detail = "测距待确认", "等待稳定的车辆识别框"
            fg, bg, border = AMBER, "#fffbeb", "#fcd34d"
        elif nearest is not None:
            index, target = nearest
            title, detail = "距离正常", f"{names[index]}最近 ≈{target.distance_m:.1f} m\n{speed_summary(target)}"
            fg, bg, border = SUCCESS, "#f0fdf4", "#86efac"
        else:
            title, detail = "监测中", "当前未检出车辆"
            fg, bg, border = MUTED, SOFT, EDGE
        state = (title, detail, fg, bg, border)
        if state != self.alert_style:
            self.alert_panel.configure(bg=bg, highlightbackground=border)
            self.alert_title.configure(text=f"实时安全预警  ·  {title}", fg=fg, bg=bg)
            self.alert_detail.configure(text=detail, fg=fg, bg=bg)
            self.alert_style = state

    def draw_path(self, vehicles, now):
        canvas = self.path_canvas
        w, h = canvas.winfo_width(), canvas.winfo_height()
        canvas.delete("all")
        if w < 45 or h < 45:
            return
        rear = self.rear_mode.get()
        far, ego = h * .12, h * (.67 if rear else .82)
        center = w / 2
        far_center = center if self.path is None else w * (.33 + .34 * self.path[1])
        lines = (self.green_lines if self.green_lines_at is not None and now - self.green_lines_at <= .8
                 else (None, None))
        self.path_lanes.configure(text=f"主摄绿色标线 · {green_lane_status(lines)}",
                                  fg=SUCCESS if any(lines) else MUTED)
        road_color = "#e1c57a"
        canvas.create_polygon(far_center-w*.08, far, far_center+w*.08, far,
                              center+w*.43, ego+h*.08, center-w*.43, ego+h*.08,
                              fill="#41434a", outline=road_color, width=2)
        for side, detected in zip((-1, 1), lines):
            if detected is None:
                canvas.create_line(far_center + side * w * .045, far, center + side * w * .22, ego+h*.08,
                                   fill="#84f45a" if self.path is not None else "#79828b", width=2)
            else:
                def project(point):
                    x, y = point
                    t = min(1., max(0., (y-.57)/.43))
                    road_center = far_center + (center-far_center)*t
                    limit = w*(.075+.35*t)
                    offset = max(-limit, min(limit, (x-.5)*w*.92))
                    return road_center+offset, far+(ego+h*.08-far)*t
                endpoints = (*project(detected.far), *project(detected.near))
                canvas.create_line(*endpoints, fill="#123f2a", width=7, capstyle="round")
                canvas.create_line(*endpoints, fill="#86f79a", width=3, capstyle="round")
        for start, end in ((.08,.13),(.22,.30),(.42,.53),(.67,.82)):
            canvas.create_line(far_center+(center-far_center)*start, far+(ego-far)*start,
                               far_center+(center-far_center)*end, far+(ego-far)*end,
                               fill="#f5f5e8", width=2)
        if rear:
            canvas.create_text(center, h * .94, text="后向", fill="#93c5fd")
        canvas.create_text(center, h * .06, text="前向", fill="#cbd5e1")
        if self.path is not None:
            start, end = self.path
            canvas.create_line(center, ego, w * (.25 + .5 * start), (ego + far) * .5,
                               w * (.33 + .34 * end), far, smooth=True, width=3, fill="#6ee7b7")
        self.car_block(canvas, center, ego, 11, "#38bdf8", "#075985")
        for index, objects in enumerate(vehicles):
            visible = sorted((t for t in objects or () if t.distance_m is not None),
                             key=lambda t: t.distance_m)[:12]
            for target in reversed(visible):
                location, depth = target.location, target.distance_m
                perspective = 1 / (1 + depth / 17)
                lateral = location - .5 if index == 0 else .5 - location
                x = center + lateral * w * (.38 + .45 * perspective)
                span = ego - far if index == 0 else h * .87 - ego
                y = ego + (-1 if index == 0 else 1) * span * (.20 + .79 * (1 - perspective))
                size = 5 + perspective * min(15, w * .065)
                roof, body = VEHICLE_GLYPH[target.level]
                self.car_block(canvas, x, y, size, roof, body)
                canvas.create_text(x, y + 9, text=f"≈{depth:.0f} m", fill=roof,
                                   font=(self.metric_font, 8))
        distances = []
        for prefix, values in zip(("前", "后"), vehicles):
            nearest = min((item.distance_m for item in values or () if item.distance_m is not None), default=None)
            distances.append(f"{prefix} ≈{nearest:.1f} m" if nearest is not None else f"{prefix} —")
        self.distance_status.configure(text="  /  ".join(distances if rear else [distances[0], "后视未启用"]))

    @staticmethod
    def car_block(canvas, x, y, size, roof, body):
        canvas.create_polygon(x-size, y-size*.4, x+size, y-size*.4, x+size, y, x-size, y,
                              fill=body, outline="#e6f6ff")
        canvas.create_polygon(x-size, y-size*.4, x-size*.56, y-size*1.32,
                              x+size*.56, y-size*1.32, x+size, y-size*.4,
                              fill=roof, outline="#e6f6ff")

    def draw_histogram(self):
        index = int(self.hist_source.get() == "副摄")
        frame = self.hist_inputs[index]
        canvas = self.hist_canvas
        canvas.delete("all")
        width = canvas.winfo_width()
        if frame is None or width < 40:
            canvas.create_text(width // 2, 36, text="等待图像", fill="#e2e8f0")
            return
        if self.raw.get() and self.frames[index] is not None:
            frame = self.frames[index][0]
        chart = render_histogram(frame, width=width, height=72)
        image = self.Image.fromarray(cv2.cvtColor(chart, cv2.COLOR_BGR2RGB))
        canvas.photo = self.ImageTk.PhotoImage(image)
        canvas.create_image(0, 0, anchor="nw", image=canvas.photo)

    def speed_button_text(self):
        return "车速参考" if self.ego_kmh is None else f"本车参考 {self.ego_kmh:g} km/h"

    def show_speed_settings(self):
        if self.speed_window is not None and self.speed_window.winfo_exists():
            self.speed_window.lift()
            return
        tk = self.tk
        dialog = self.speed_window = tk.Toplevel(self.root)
        dialog.title("车辆速度显示")
        dialog.transient(self.root)
        dialog.configure(bg=CARD)
        dialog.resizable(False, False)
        content = tk.Frame(dialog, bg=CARD)
        content.pack(fill="both", padx=18, pady=14)
        self.label(content, "本车速度参考（km/h）", 13, bold=True).pack(anchor="w")
        self.label(content, "可输入片源标注的本车速度，用于估算同向车辆的车速。\n"
                   "留空时显示相对速度，正值接近，负值远离。",
                   10, MUTED, justify="left").pack(anchor="w", pady=(5, 9))
        value = tk.StringVar(value="" if self.ego_kmh is None else f"{self.ego_kmh:g}")
        field = self.ttk.Entry(content, textvariable=value, width=12)
        field.pack(anchor="w")
        hint = self.label(content, "", 10, AMBER)
        hint.pack(anchor="w", pady=4)

        def save(_event=None):
            raw = value.get().strip()
            try:
                speed = float(raw) if raw else None
                if speed is not None and not 0 <= speed <= 180:
                    raise ValueError
            except ValueError:
                hint.configure(text="请输入 0–180，或留空")
                return
            self.ego_kmh = speed
            self.speed_button.configure(text=self.speed_button_text())
            dialog.destroy()

        self.button(content, "应用", save, primary=True).pack(side="right")
        self.button(content, "取消", dialog.destroy).pack(side="right", padx=6)
        field.bind("<Return>", save)
        dialog.bind("<Escape>", lambda _: (dialog.destroy(), "break")[1])
        field.focus_set()

    def show_tuning(self):
        if self.tuning_window is not None and self.tuning_window.winfo_exists():
            self.tuning_window.lift()
            return
        tk = self.tk
        dialog = self.tuning_window = tk.Toplevel(self.root)
        dialog.title("RK 图像与识别调参")
        dialog.transient(self.root)
        dialog.configure(bg=CARD)
        dialog.geometry("550x550")
        header = tk.Frame(dialog, bg=CARD)
        header.pack(fill="x", padx=16, pady=10)
        self.label(header, "ARM 图像处理", 14, bold=True).pack(side="left")
        source = tk.StringVar(value="主摄")
        selector = self.ttk.Combobox(header, textvariable=source, values=("主摄", "副摄"),
                                     state="readonly", width=7)
        selector.pack(side="right")
        mode = tk.Frame(dialog, bg=CARD)
        mode.pack(fill="x", padx=16)
        enabled, preset = tk.BooleanVar(), tk.StringVar()
        variables = {}

        def index():
            return int(source.get() == "副摄")

        def change(name, value):
            i = index()
            if name in ("min_score", "box_width"):
                score, width = self.detector_controls[i]
                score, width = (float(value), width) if name == "min_score" else (score, round(float(value)))
                self.detector_controls[i] = score, width
                channel = self.channels[i]
                if channel is not None:
                    channel.min_score, channel.box_width = score, width
            else:
                self.isp_params[i].set(name, value)

        self.ttk.Checkbutton(mode, text="启用 RK 图像处理", variable=enabled,
                             command=lambda: change("enable", enabled.get())).pack(side="left")
        preset_box = self.ttk.Combobox(mode, textvariable=preset, values=tuple(arm_isp.PRESETS),
                                       state="readonly", width=8)
        preset_box.pack(side="right")
        self.label(mode, "色彩预设", 10, MUTED).pack(side="right", padx=6)
        preset_box.bind("<<ComboboxSelected>>", lambda _: change("ccm_preset", preset.get()))
        sliders = tk.Frame(dialog, bg=CARD)
        sliders.pack(fill="x", padx=16, pady=8)
        sliders.columnconfigure(1, weight=1)
        specs = [(name, label, arm_isp.DEFS[name][1], arm_isp.DEFS[name][2], .01)
                 for name, label in ISP_SLIDERS]
        specs += [("min_score", "检测置信度下限", .25, .95, .01), ("box_width", "目标框线宽", 1, 6, 1)]
        for row, (name, label, low, high, step) in enumerate(specs):
            variable = variables[name] = tk.DoubleVar()
            self.label(sliders, label, 10, MUTED, anchor="w").grid(row=row, column=0, sticky="w", padx=(0, 8))
            tk.Scale(sliders, from_=low, to=high, resolution=step, variable=variable,
                     orient="horizontal", bg=CARD, fg=INK, highlightthickness=0,
                     command=lambda value, key=name: change(key, value)).grid(row=row, column=1, sticky="ew")

        def load_controls():
            i = index()
            values = self.isp_params[i].get()
            enabled.set(values["enable"])
            preset.set(values["ccm_preset"])
            values["min_score"], values["box_width"] = self.detector_controls[i]
            for key, variable in variables.items():
                variable.set(values[key])

        def reset():
            i = index()
            self.isp_params[i].reset()
            self.isp_params[i].set("enable", 0)
            change("min_score", .30)
            change("box_width", 2)
            load_controls()

        selector.bind("<<ComboboxSelected>>", lambda _: load_controls())
        footer = tk.Frame(dialog, bg=CARD)
        footer.pack(fill="x", padx=16, pady=(0, 8))
        self.label(footer, "图像参数作用于当前通道", 9, MUTED).pack(side="left")
        self.button(footer, "恢复默认", reset).pack(side="right")
        load_controls()

    def reopen_aux(self):
        channel = self.channels[1]
        if channel is not None:
            self.open(1, channel.source, flip_vertical=channel.flip_vertical, screen=channel.screen)

    def choose(self, index):
        path = self.filedialog.askopenfilename(
            initialdir=self.args.media_dir, filetypes=[("视频", "*.mp4 *.avi *.mkv *.mov"), ("全部", "*")])
        if path:
            self.open(index, path)

    def calibrate_screen(self, index):
        tk = self.tk
        channel = self.channels[index]
        live = channel is not None and channel.source.startswith(("http://", "https://"))
        dialog = tk.Toplevel(self.root)
        dialog.title(f"CH 0{index + 1} 屏幕标定")
        dialog.transient(self.root)
        dialog.configure(bg=CARD)
        dialog.geometry("820x560")
        dialog.minsize(460, 320)
        dialog.grab_set()
        self.label(dialog, "依次点击屏幕内角：左上 → 右上 → 右下 → 左下", 12, bold=True
                   ).pack(anchor="w", padx=16, pady=(12, 6))
        footer = tk.Frame(dialog, bg=CARD)
        footer.pack(side="bottom", fill="x", padx=16, pady=8)
        hint = self.label(footer, "", 10, MUTED, anchor="w")
        hint.pack(fill="x", pady=(0, 6))
        actions = tk.Frame(footer, bg=CARD)
        actions.pack(fill="x")
        canvas = tk.Canvas(dialog, bg=INK, highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True, padx=16)
        image = None
        stamp = None
        preview_timer = None
        waiting = "等待相机画面…" if live else "请先连接 FPGA 实时输入，再打开屏幕标定"
        points = []
        image_box = None

        def draw(_event=None):
            nonlocal image_box
            w, h = canvas.winfo_width(), canvas.winfo_height()
            canvas.delete("all")
            image_box = None
            if image is None:
                canvas.photo = None
                canvas.create_text(w // 2, h // 2, text=waiting, fill="white", width=max(1, w - 32))
                return
            if w <= 1 or h <= 1:
                return
            scale = min(w / image.width, h / image.height)
            iw, ih = max(1, round(image.width * scale)), max(1, round(image.height * scale))
            left, top = (w - iw) // 2, (h - ih) // 2
            image_box = (left, top, iw, ih)
            canvas.photo = self.ImageTk.PhotoImage(
                image.resize((iw, ih), self.Image.Resampling.BILINEAR), master=canvas)
            canvas.create_image(left, top, anchor="nw", image=canvas.photo)
            positions = [(left + x * (iw - 1), top + y * (ih - 1)) for x, y in points]
            if len(positions) >= 2:
                path = positions + positions[:1] if len(positions) == 4 else positions
                canvas.create_line(*[value for point in path for value in point], fill=ACCENT, width=2)
            for n, (x, y) in enumerate(positions, start=1):
                canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=ACCENT, outline="")
                canvas.create_text(x + 11, y - 9, text=str(n), fill=ACCENT, font=(self.metric_font, 12, "bold"))

        def pick(event):
            if image_box is None or len(points) == 4:
                return
            left, top, w, h = image_box
            if w <= 1 or h <= 1 or not (left <= event.x < left + w and top <= event.y < top + h):
                return
            points.append(((event.x - left) / (w - 1), (event.y - top) / (h - 1)))
            hint.configure(text=f"画面已冻结 · 已选 {len(points)} / 4", fg=MUTED)
            retake.state(["!disabled"])
            if len(points) == 4:
                apply.state(["!disabled"])
            draw()

        def update_preview():
            nonlocal image, stamp, preview_timer
            if not points:
                sample = channel.calibration_frame
                if sample is not None and time.monotonic() - sample[0] <= 2:
                    if sample[0] != stamp:
                        stamp, frame = sample
                        image = self.Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                        draw()
                    hint.configure(text="实时原图 · 点击第一个内角后冻结画面", fg=MUTED)
                else:
                    hint.configure(text="当前没有新帧，正在等待相机信号", fg=AMBER)
                    if image is not None:
                        image, stamp = None, None
                        draw()
            preview_timer = dialog.after(200, update_preview)

        def reset():
            nonlocal preview_timer
            points.clear()
            apply.state(["disabled"])
            retake.state(["disabled"])
            dialog.after_cancel(preview_timer)
            update_preview()
            draw()

        def close(_event=None):
            if preview_timer is not None:
                dialog.after_cancel(preview_timer)
            dialog.destroy()
            return "break"

        def save():
            try:
                corners = screen_corners(points)
                screens = self.screens.copy()
                screens[index] = corners
                temp = self.screen_config.with_suffix(self.screen_config.suffix + ".tmp")
                temp.parent.mkdir(parents=True, exist_ok=True)
                temp.write_text(json.dumps(dict(zip(SCREEN_KEYS, screens))), encoding="utf-8")
                temp.replace(self.screen_config)
            except (OSError, ValueError) as exc:
                hint.configure(text=str(exc), fg=AMBER)
                return
            self.screens = screens
            close()
            self.open(index, channel.source, flip_vertical=channel.flip_vertical, screen=corners)

        apply = self.button(actions, "应用标定", save, primary=True)
        apply.pack(side="right")
        apply.state(["disabled"])
        retake = self.button(actions, "重新取帧", reset)
        retake.pack(side="right", padx=8)
        retake.state(["disabled"])
        self.button(actions, "取消", close).pack(side="left")
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", close)
        canvas.bind("<Configure>", draw)
        canvas.bind("<Button-1>", pick)
        if live:
            update_preview()
        else:
            hint.configure(text="标定仅用于 FPGA 实时输入", fg=AMBER)

    def open_fpga(self):
        for index in range(2):
            self.open(index, f"{self.args.endpoint.rstrip('/')}/frame?cam={index}",
                      flip_vertical=(index == 0),
                      screen=self.screens[index])

    def open(self, index, source, *, flip_vertical=False, screen=None):
        if index == 0:
            self.path = None
            self.green_lines = (None, None)
            self.green_lines_at = None
        if self.channels[index] is not None:
            self.channels[index].stop.set()
        self.frames[index] = None
        self.objects[index] = []
        self.vehicle_updated[index] = None
        self.hist_inputs[index] = None
        label, canvas, state = self.cards[index]
        self.histories[index].clear()
        self.rendered[index] = None
        live = source.startswith(("http://", "https://"))
        if index == 0:
            self.recording_lanes.state(["disabled"] if live else ["!disabled"])
        if live:
            title = ("J2 / IMX415", "J3 / CS500")[index]
            label.configure(text=f"FPGA 实时输入   ·   {title}")
        else:
            name = Path(source).name
            label.configure(text=f"录播   ·   {name if len(name) <= 44 else name[:41] + '…'}")
        canvas.delete("all")
        state.configure(text="连接中", fg=MUTED)
        for value in self.metrics[index]:
            value.configure(text="—")
        helper = getattr(self.args, "yolo_helper", None)
        model = getattr(self.args, "yolo_model", None)
        backend = (helper, model, 1 << index) if helper and model else None
        detect_every = (getattr(self.args, "main_detect_every", 3),
                        getattr(self.args, "aux_detect_every", 2))[index]
        width = (getattr(self.args, "main_width", None) or self.args.width) if index == 0 else self.args.width
        self.channels[index] = Channel(source, width, index=index, flip_vertical=flip_vertical,
                                       screen=screen, screen_only=live and self.screen_only,
                                       detector_backend=backend, detect_every=detect_every,
                                       rear_view=index == 1 and self.rear_mode.get(),
                                       focal_ratio=getattr(self.args, ("front_focal", "rear_focal")[index], .9),
                                       near_m=getattr(self.args, "near_alert_m", 10.),
                                       isp=self.isp_params[index], alert_relay=self.alert_relay)
        self.channels[index].min_score, self.channels[index].box_width = self.detector_controls[index]

    def show_result(self, index, result):
        original, output, status, _ = result
        source, _, state = self.cards[index]
        metrics = self.metrics[index]
        self.objects[index] = status[9] if original is not None else []
        self.hist_inputs[index] = status[10] if original is not None else None
        self.vehicle_updated[index] = status[11] if original is not None else None
        if index == 0:
            self.path = status[8] if original is not None else None
            self.green_lines = status[12] if original is not None else (None, None)
            self.green_lines_at = status[13] if original is not None else None
        if original is None:
            state.configure(text="录播结束" if status == "录播结束" else "信号不可用", fg=AMBER)
            if status != "录播结束":
                source.configure(text=status[:72])
                self.frames[index] = None
            for value in metrics:
                value.configure(text="—")
            return
        channel = self.channels[index]
        live = channel.source.startswith(("http://", "https://"))
        if channel.screen_pending:
            state.configure(text="待标定", fg=AMBER)
        else:
            state.configure(text="屏幕内" if live and channel.screen is not None else "实时" if live else "录播",
                            fg=SUCCESS)
        for label, value in zip(metrics, status):
            label.configure(text=value)
        self.frames[index] = (original, output)
        now = time.monotonic()
        history = self.histories[index]
        values = (float(status[1]) if status[1] != "—" else None,
                  int(status[5]) if status[5].isdigit() else None)
        if not history or now - history[-1][0] >= .16:
            history.append((now, values))

    def refresh(self):
        settings = (self.weather.get(), self.dehaze.get(), self.multiscale.get(), self.lanes.get())
        raw = self.raw.get()
        updated = [False, False]
        for index, channel in enumerate(self.channels):
            if channel is None:
                continue
            live = channel.source.startswith(("http://", "https://"))
            channel.settings = (*settings[:3], False) if live else settings
            channel.ego_kmh = self.ego_kmh
            try:
                result = channel.latest.get_nowait()
            except Empty:
                continue
            self.show_result(index, result)
            updated[index] = True
        for index, (_, canvas, _) in enumerate(self.cards):
            size = (canvas.winfo_width(), canvas.winfo_height(), raw)
            if not updated[index] and self.rendered[index] == size:
                continue
            self.rendered[index] = size
            canvas.delete("all")
            if self.frames[index] is None:
                canvas.create_text(size[0] // 2, size[1] // 2, text="等待视频信号",
                                   fill=MUTED, font=("TkDefaultFont", 11))
                continue
            frame = self.frames[index][0 if raw else 1]
            image = self.Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            scale = min(size[0] / image.width, size[1] / image.height)
            fit = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            image = image.resize(fit, self.Image.Resampling.BILINEAR)
            canvas.photo = self.ImageTk.PhotoImage(image)
            canvas.create_image(size[0] // 2, size[1] // 2, image=canvas.photo)
        now = time.monotonic()
        now_processing = time.perf_counter()
        vehicles = self.fresh_vehicles(now_processing)
        self.draw_safety(vehicles)
        if now >= self.chart_refresh:
            self.draw_charts(now)
            self.draw_path(vehicles, now_processing)
            self.draw_histogram()
            self.chart_refresh = now + .25
        self.root.after(30, self.refresh)

    def close(self):
        for channel in self.channels:
            if channel is not None:
                channel.stop.set()
        self.root.destroy()
        if self.alert_relay is not None:
            self.alert_relay.close()


def main():
    import tkinter as tk

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fpga", action="store_true")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8080")
    parser.add_argument("--video-a")
    parser.add_argument("--video-b")
    parser.add_argument("--media-dir", default=str(Path.cwd()))
    parser.add_argument("--width", type=int, default=960, help="maximum processing width")
    parser.add_argument("--main-width", type=int, help="override main-camera processing width")
    parser.add_argument("--windowed", action="store_true", help="start in a window instead of fullscreen")
    parser.add_argument("--yolo-helper", help="path to the FPGA project's rk_yolo_srv executable")
    parser.add_argument("--yolo-model", help="path to its 640-pixel YOLOv8 RKNN model")
    parser.add_argument("--main-detect-every", type=int, default=3,
                        help="run main-camera YOLO every N frames, with optical flow between detections")
    parser.add_argument("--aux-detect-every", type=int, default=2,
                        help="run secondary-camera YOLO every N frames")
    parser.add_argument("--main-screen", nargs=8, type=float, metavar="COORD",
                        help="normalized screen corners, clockwise from top left after flip")
    parser.add_argument("--aux-screen", nargs=8, type=float, metavar="COORD",
                        help="normalized secondary screen corners, clockwise from top left")
    parser.add_argument("--aux-rear", action="store_true", help="enable vehicle ranging on a rear-facing secondary camera")
    parser.add_argument("--front-focal", type=float, default=.9, help="front calibrated fx divided by frame width")
    parser.add_argument("--rear-focal", type=float, default=.9, help="rear calibrated fx divided by frame width")
    parser.add_argument("--near-alert-m", type=float, default=10.,
                        help="close-vehicle warning threshold in estimated meters (demo)")
    parser.add_argument("--ego-kmh", type=float, help="optional manual ego speed for same-direction estimates")
    parser.add_argument("--alert-port", type=int, help="enable the loopback PC alert relay on this port")
    parser.add_argument("--alert-db", default="alert-spool.sqlite3")
    parser.add_argument("--screen-config", default="screen-roi.json")
    parser.add_argument("--screen-only", action="store_true",
                        help="pause live recognition until each HDMI screen is calibrated")
    args = parser.parse_args()
    if not all(.1 <= value <= 10 for value in (args.front_focal, args.rear_focal)):
        parser.error("focal ratios must be in [0.1, 10]")
    if not 2 <= args.near_alert_m <= 40:
        parser.error("--near-alert-m must be between 2 and 40")
    if args.ego_kmh is not None and not 0 <= args.ego_kmh <= 180:
        parser.error("--ego-kmh must be between 0 and 180")
    if args.alert_port is not None and not 1 <= args.alert_port <= 65535:
        parser.error("--alert-port must be between 1 and 65535")
    if args.width < 64:
        parser.error("--width must be at least 64")
    if args.main_width is not None and args.main_width < 64:
        parser.error("--main-width must be at least 64")
    if args.fpga and (args.video_a or args.video_b):
        parser.error("--fpga cannot be combined with recording arguments")
    if bool(args.yolo_helper) != bool(args.yolo_model):
        parser.error("--yolo-helper and --yolo-model must be supplied together")
    if not 1 <= args.main_detect_every <= 6:
        parser.error("--main-detect-every must be between 1 and 6")
    if not 1 <= args.aux_detect_every <= 6:
        parser.error("--aux-detect-every must be between 1 and 6")
    for corners in (args.main_screen, args.aux_screen):
        if corners is not None:
            try:
                screen_corners(corners)
            except ValueError as exc:
                parser.error(str(exc))
    cv2.setNumThreads(1)
    root = tk.Tk()
    Console(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
