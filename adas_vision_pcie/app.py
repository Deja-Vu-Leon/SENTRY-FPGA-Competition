"""ADAS research dashboard for FPGA PCIe video + RK3576 RKNN YOLOv8."""
import argparse
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from tkinter import filedialog, simpledialog
import cv2
import numpy as np
from PIL import Image, ImageTk
from tracker import Tracker
from vision import Detection, NoModelDetector, PCYOLODetector, RKNNDetector
from lane import LaneAnalyzer
from weather import enhance, MODES
from histogram import render_histogram
from event_log import EventLogger
from road_view import paint_lane_region, render_road_scene

BG, PANEL, PANEL2, FG, MUTED, GREEN = "#0b1420", "#142338", "#1d3148", "#eaf3ff", "#9aadc3", "#35d4b2"
COLORS = {"高": (65, 73, 245), "中": (66, 175, 255), "低": (120, 210, 66),
          "未就绪": (190, 170, 140), "暂失": (135, 145, 155)}


class Dashboard:
    def __init__(self, root, args):
        self.root, self.args = root, args
        root.title("SENTRY | 多目标防碰撞研究平台")
        root.geometry("1380x760")
        root.minsize(1040, 620)
        root.configure(bg=BG)
        self.cap = None
        self.demo = True
        self.pcie = False
        self.video_ended = False
        self.video_frame = 0
        self.video_fps = 25.0
        self.model = NoModelDetector()
        self.tracker = Tracker()
        self.lane = LaneAnalyzer()
        self.frame_count = 0
        self.last_time = time.monotonic()
        self.logger = EventLogger(args.log_dir, max_mb=args.log_max_mb)
        self.logger.record("session_start", {"mode": "PC or RK3576"})
        self.source_name = "demo"
        self.status = tk.StringVar(value="演示模式 · 模拟框与运动，不代表实际识别")
        self.ego = tk.DoubleVar(value=args.ego_kmh)
        self.focal = tk.DoubleVar(value=args.focal_px)
        self.reaction = tk.DoubleVar(value=args.reaction_s)
        self.decel = tk.DoubleVar(value=args.decel_mps2)
        self.enabled = tk.BooleanVar(value=True)
        self.lane_enabled = tk.BooleanVar(value=True)
        self.guidance = tk.StringVar(value="车道保持辅助：等待视频")
        self.scene_summary = tk.StringVar(value="车辆 --   最高风险 --\n车道 --   最近 --")
        self.weather_enabled = tk.BooleanVar(value=args.weather_on)
        self.weather_mode = tk.StringVar(value=args.weather_mode)
        self.weather_strength = tk.IntVar(value=args.weather_strength)
        self.weather_signature = None
        self.hist_enabled = tk.BooleanVar(value=True)
        self.log_enabled = tk.BooleanVar(value=True)
        self.display_blend = tk.IntVar(value=100)
        self.preview_mode = tk.StringVar(value="原图")
        self.lane_defaults = {
            "白线亮度阈值": 155, "边缘低阈值": 60, "边缘高阈值": 160,
            "ROI 顶部高度 %": 55, "ROI 顶部半宽 %": 10,
            "ROI 底部半宽 %": 44, "直线投票阈值": 35,
            "最短线段 %": 6, "偏离阈值 %": 22,
        }
        self.lane_vars = {key: tk.IntVar(value=value) for key, value in self.lane_defaults.items()}
        self._build()
        if args.model:
            self.load_model(args.model)
        if args.pc_model:
            self.load_pc_model(args.pc_model)
        if args.pcie_device:
            self.open_source(args.pcie_device, True)
        elif args.video:
            self.open_source(args.video, False)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(30, self.tick)

    def label(self, parent, text, size=10, color=FG, bold=False, bg=PANEL, **kw):
        x = tk.Label(parent, text=text, fg=color, bg=bg,
                     font=("Microsoft YaHei UI", size, "bold" if bold else "normal"), **kw)
        return x

    def button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, bg=PANEL2, fg=FG, bd=0,
                         activebackground=GREEN, activeforeground=BG, cursor="hand2",
                         font=("Microsoft YaHei UI", 10, "bold"), padx=12, pady=9)

    def _build(self):
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=24, pady=(15, 12))
        self.label(head, "◈  SENTRY", 22, GREEN, True, BG).pack(side="left")
        self.label(head, "  /  多目标防碰撞研究平台", 12, MUTED, bg=BG).pack(side="left")
        self.label(head, "PH1A90 → PCIe → RK3576", 10, MUTED, bg=BG).pack(side="right")
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=24)
        side = tk.Frame(body, bg=PANEL, width=250)
        side.pack(side="left", fill="y", padx=(0, 14))
        side.pack_propagate(False)
        side_canvas = tk.Canvas(side, bg=PANEL, highlightthickness=0, width=230)
        side_canvas.pack(side="left", fill="both", expand=True)
        side_bar = tk.Scrollbar(side, orient="vertical", command=side_canvas.yview)
        side_bar.pack(side="right", fill="y")
        side_canvas.configure(yscrollcommand=side_bar.set)
        side_content = tk.Frame(side_canvas, bg=PANEL)
        side_window = side_canvas.create_window((0, 0), window=side_content, anchor="nw")
        side_content.bind("<Configure>", lambda e: side_canvas.configure(scrollregion=side_canvas.bbox("all")))
        side_canvas.bind("<Configure>", lambda e: side_canvas.itemconfigure(side_window, width=e.width))
        side = side_content
        self.label(side, "输入与模型", 14, bold=True).pack(anchor="w", padx=16, pady=(20, 10))
        for title, fn in (("FPGA PCIe 视频节点", self.choose_pcie),
                          ("本地视频", self.choose_video), ("演示场景", self.use_demo),
                          ("加载 PC YOLO 模型", self.choose_pc_model),
                          ("加载 RKNN 模型", self.choose_model)):
            self.button(side, title, fn).pack(fill="x", padx=12, pady=5)
        self.label(side, "监测目标", 13, bold=True).pack(anchor="w", padx=16, pady=(26, 9))
        for name in ("car  小汽车", "bus  公交车", "truck  卡车", "bike  自行车", "motorbike  摩托车"):
            self.label(side, "▣  " + name, 10, MUTED).pack(anchor="w", padx=20, pady=5)
        tk.Checkbutton(side, text="启用防碰撞分析", variable=self.enabled, bg=PANEL,
                       fg=FG, selectcolor=PANEL2, activebackground=PANEL,
                       activeforeground=FG, font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=15, pady=(20, 0))
        tk.Checkbutton(side, text="车道线 / 偏离预警", variable=self.lane_enabled, bg=PANEL,
                       fg=FG, selectcolor=PANEL2, activebackground=PANEL,
                       activeforeground=FG, font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=15, pady=4)
        tk.Checkbutton(side, text="极端天气画面增强", variable=self.weather_enabled, bg=PANEL,
                       fg=FG, selectcolor=PANEL2, activebackground=PANEL,
                       activeforeground=FG, font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=15, pady=4)
        tk.Checkbutton(side, text="显示 RGB 直方图", variable=self.hist_enabled, bg=PANEL,
                       fg=FG, selectcolor=PANEL2, activebackground=PANEL,
                       activeforeground=FG, font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=15, pady=4)
        tk.Checkbutton(side, text="保存危险画面日志", variable=self.log_enabled, bg=PANEL,
                       fg=FG, selectcolor=PANEL2, activebackground=PANEL,
                       activeforeground=FG, font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=15, pady=4)
        self.button(side, "打开 logs 文件夹", self.open_logs).pack(fill="x", padx=12, pady=(8, 2))
        self.label(side, "估算值仅用于研发验证", 9, MUTED).pack(anchor="w", padx=20, pady=10)
        tuning = tk.Frame(body, bg=PANEL, width=260)
        tuning.pack(side="right", fill="y", padx=(14, 0))
        tuning.pack_propagate(False)
        summary_card = tk.Frame(tuning, bg=PANEL2)
        summary_card.pack(fill="x", padx=8, pady=(8, 4))
        self.label(summary_card, "实时场景摘要", 11, GREEN, True, PANEL2).pack(anchor="w", padx=9, pady=(7, 2))
        self.label(summary_card, "", 9, FG, bg=PANEL2, textvariable=self.scene_summary,
                   justify="left", anchor="w").pack(fill="x", padx=9, pady=(0, 8))
        self.label(tuning, "参数调整", 14, bold=True).pack(anchor="w", padx=14, pady=(12, 5))
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Sentry.TNotebook", background=PANEL, borderwidth=0)
        style.configure("Sentry.TNotebook.Tab", background=PANEL2, foreground=FG,
                        padding=(10, 7), font=("Microsoft YaHei UI", 9))
        style.map("Sentry.TNotebook.Tab", background=[("selected", "#27615b")],
                  foreground=[("selected", FG)])
        tabs = ttk.Notebook(tuning, style="Sentry.TNotebook")
        tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        weather_tab = tk.Frame(tabs, bg=PANEL)
        threshold_tab = tk.Frame(tabs, bg=PANEL)
        roi_tab = tk.Frame(tabs, bg=PANEL)
        tabs.add(weather_tab, text="天气")
        tabs.add(threshold_tab, text="阈值")
        tabs.add(roi_tab, text="ROI")
        self.label(weather_tab, "极端天气增强", 12, bold=True).pack(anchor="w", padx=8, pady=(14, 8))
        weather_option = tk.OptionMenu(weather_tab, self.weather_mode, *MODES)
        weather_option.config(bg=PANEL2, fg=FG, activebackground=GREEN, relief="flat", bd=0,
                              highlightthickness=0, font=("Microsoft YaHei UI", 10))
        weather_option["menu"].config(bg=PANEL2, fg=FG)
        weather_option.pack(fill="x", padx=8, pady=(0, 5))
        tk.Scale(weather_tab, label="增强强度 %", from_=0, to=100, variable=self.weather_strength,
                 orient="horizontal", length=225, bg=PANEL, fg=FG, troughcolor=PANEL2,
                 activebackground=GREEN, highlightthickness=0,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=8)
        tk.Scale(weather_tab, label="显示比例：原图 0 / 增强 100", from_=0, to=100,
                 variable=self.display_blend, orient="horizontal", length=225,
                 bg=PANEL, fg=FG, troughcolor=PANEL2, activebackground=GREEN,
                 highlightthickness=0, font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=8)
        self.label(weather_tab, "默认关闭；过强可能降低识别率", 9, MUTED).pack(anchor="w", padx=8, pady=8)
        self.label(threshold_tab, "二值化与边缘检测", 12, bold=True).pack(anchor="w", padx=8, pady=(14, 8))
        option = tk.OptionMenu(threshold_tab, self.preview_mode, "原图", "二值图", "边缘图")
        option.config(bg=PANEL2, fg=FG, activebackground=GREEN, relief="flat", bd=0,
                      highlightthickness=0, font=("Microsoft YaHei UI", 10))
        option["menu"].config(bg=PANEL2, fg=FG)
        option.pack(fill="x", padx=8, pady=(0, 8))
        specs = (
            (threshold_tab, "白线亮度阈值", 50, 250),
            (threshold_tab, "边缘低阈值", 10, 200),
            (threshold_tab, "边缘高阈值", 30, 255),
            (roi_tab, "ROI 顶部高度 %", 35, 80),
            (roi_tab, "ROI 顶部半宽 %", 5, 25),
            (roi_tab, "ROI 底部半宽 %", 25, 49),
            (roi_tab, "直线投票阈值", 10, 100),
            (roi_tab, "最短线段 %", 2, 20),
            (roi_tab, "偏离阈值 %", 10, 40),
        )
        for parent, title, lo, hi in specs:
            tk.Scale(parent, label=title, from_=lo, to=hi, variable=self.lane_vars[title],
                     orient="horizontal", length=225, bg=PANEL, fg=FG, troughcolor=PANEL2,
                     activebackground=GREEN, highlightthickness=0,
                     font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=8, pady=1)
        self.button(roi_tab, "恢复默认", self.reset_lane_controls).pack(fill="x", padx=8, pady=(8, 10))
        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        bar = tk.Frame(main, bg=PANEL)
        bar.pack(fill="x")
        self.label(bar, "LIVE  /  目标跟踪", 12, GREEN, True).pack(side="left", padx=16, pady=12)
        self.label(bar, "车辆框选 · 车道线 · 偏离预警", 9, MUTED).pack(side="right", padx=16)
        self.visual_row = tk.Frame(main, bg=BG)
        self.visual_row.pack(fill="both", expand=True, pady=(8, 8))
        self.preview = tk.Canvas(self.visual_row, bg="#07101b", highlightthickness=0, width=320, height=180)
        self.preview.pack(side="left", fill="both", expand=True)
        self.road_preview = tk.Canvas(self.visual_row, bg="#0b1119", highlightthickness=0,
                                      width=180, height=180)
        self.road_preview.pack(side="right", fill="y", padx=(6, 0))
        self.visual_row.bind("<Configure>", self._size_road_panel)
        self.histogram_panel = tk.Frame(main, bg=PANEL)
        self.histogram_panel.pack(fill="x", pady=(0, 8))
        self.label(self.histogram_panel, "RGB 直方图", 10, GREEN, True).pack(side="left", padx=12)
        self.histogram_view = tk.Label(self.histogram_panel, bg=PANEL)
        self.histogram_view.pack(side="left", padx=8, pady=5)
        tiles = tk.Frame(main, bg=BG)
        tiles.pack(fill="x")
        self.metrics = {}
        for title in ("目标数", "最近目标", "最高风险", "车道状态", "帧率"):
            tile = tk.Frame(tiles, bg=PANEL)
            tile.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.label(tile, title, 9, MUTED).pack(anchor="w", padx=13, pady=(9, 2))
            v = self.label(tile, "--", 16, GREEN, True)
            v.pack(anchor="w", padx=13, pady=(0, 10))
            self.metrics[title] = v
        settings = tk.Frame(main, bg=PANEL)
        settings.pack(fill="x", pady=(10, 0))
        self.label(settings, "参数", 11, bold=True).pack(side="left", padx=(8, 6), pady=8)
        fields = tk.Frame(settings, bg=PANEL)
        fields.pack(side="left", fill="x", expand=True)
        for index, (title, var) in enumerate((("自车 km/h", self.ego), ("焦距 px", self.focal),
                                               ("反应 s", self.reaction), ("减速度 m/s²", self.decel))):
            cell = tk.Frame(fields, bg=PANEL)
            cell.grid(row=index//2, column=index%2, sticky="w", padx=4, pady=2)
            self.label(cell, title, 9, MUTED).pack(side="left", padx=(0, 3))
            tk.Entry(cell, textvariable=var, width=6, bg=PANEL2, fg=FG,
                     insertbackground=FG, bd=0, justify="center").pack(side="left")
        lane_bar = tk.Frame(main, bg=PANEL)
        lane_bar.pack(fill="x", pady=(7, 0))
        self.label(lane_bar, "车道保持辅助", 10, GREEN, True).pack(side="left", padx=(12, 10), pady=7)
        self.label(lane_bar, "", 10, FG, textvariable=self.guidance).pack(side="left", pady=7)
        foot = tk.Frame(self.root, bg=BG)
        foot.pack(fill="x", padx=24, pady=10)
        self.label(foot, "●  ", 10, GREEN, bg=BG).pack(side="left")
        self.label(foot, "", 9, FG, bg=BG, textvariable=self.status).pack(side="left")
        self.label(foot, "非实车安全系统", 9, MUTED, bg=BG).pack(side="right")

    def reset_lane_controls(self):
        for key, value in self.lane_defaults.items():
            self.lane_vars[key].set(value)
        self.lane.reset()

    def _size_road_panel(self, event):
        self.road_preview.configure(width=min(260, max(130, int(event.width*.27))))

    def open_logs(self):
        import os
        if hasattr(os, "startfile"):
            os.startfile(self.logger.directory)
        else:
            self.status.set(f"日志目录：{self.logger.directory}")

    def apply_lane_controls(self):
        values = {key: var.get() for key, var in self.lane_vars.items()}
        self.lane.white_min = values["白线亮度阈值"]
        self.lane.canny_low = values["边缘低阈值"]
        self.lane.canny_high = max(self.lane.canny_low + 1, values["边缘高阈值"])
        self.lane.roi_top_pct = values["ROI 顶部高度 %"]
        self.lane.roi_top_half_pct = values["ROI 顶部半宽 %"]
        self.lane.roi_bottom_half_pct = max(self.lane.roi_top_half_pct + 5, values["ROI 底部半宽 %"])
        self.lane.hough_votes = values["直线投票阈值"]
        self.lane.min_line_pct = values["最短线段 %"]
        self.lane.departure_threshold = values["偏离阈值 %"] / 100

    def process_weather(self, frame):
        signature = (self.weather_enabled.get(), self.weather_mode.get(), self.weather_strength.get())
        if signature != self.weather_signature:
            self.weather_signature = signature
            self.tracker = Tracker()
            self.lane.reset()
        if not signature[0]:
            return frame
        try:
            return enhance(frame, signature[1], signature[2])
        except Exception as exc:
            self.status.set(f"天气增强失败，使用原画：{exc}")
            return frame

    def choose_pcie(self):
        path = simpledialog.askstring("PCIe 视频节点", "输入 FPGA PCIe 驱动提供的 V4L2 节点：",
                                      initialvalue="/dev/video0", parent=self.root)
        if path:
            self.open_source(path, True)

    def choose_video(self):
        path = filedialog.askopenfilename(filetypes=[("视频文件", "*.mp4 *.avi *.mov *.mkv"), ("全部", "*.*")])
        if path:
            self.open_source(path, False)

    def choose_model(self):
        path = filedialog.askopenfilename(filetypes=[("RKNN 模型", "*.rknn")])
        if path:
            self.load_model(path)

    def choose_pc_model(self):
        path = filedialog.askopenfilename(filetypes=[("YOLO PyTorch 模型", "*.pt")])
        if path:
            self.load_pc_model(path)

    def load_pc_model(self, path):
        try:
            candidate = PCYOLODetector(path)
        except Exception as exc:
            self.status.set(f"PC YOLO 加载失败：{exc}")
            return
        self.model.close()
        self.model = candidate
        self.tracker = Tracker()
        self.status.set(f"已加载 PC YOLO 模型：{path}")

    def load_model(self, path):
        try:
            candidate = RKNNDetector(path)
        except Exception as exc:
            self.status.set(f"RKNN 加载失败：{exc}")
            return
        self.model.close()
        self.model = candidate
        self.tracker = Tracker()
        self.status.set(f"已加载 RKNN 模型：{path}")

    def open_source(self, path, pcie):
        if pcie and str(path).startswith(("http://", "https://")):
            from fpga_capture import FpgaCapture
            cap = FpgaCapture(path)
        else:
            cap = cv2.VideoCapture(path, cv2.CAP_V4L2) if pcie else cv2.VideoCapture(path)
        if not cap.isOpened():
            cap.release()
            self.status.set(f"打开失败：{path} {getattr(cap, 'error', '')}")
            return
        if self.cap:
            self.cap.release()
        self.cap, self.demo, self.pcie, self.video_ended = cap, False, pcie, False
        self.source_name = str(path)
        self.logger.record("source_open", {"source": self.source_name, "pcie": pcie})
        self.video_frame = 0
        fps = cap.get(cv2.CAP_PROP_FPS)
        self.video_fps = fps if np.isfinite(fps) and fps > 0 else 25.0
        self.tracker = Tracker()
        self.lane.reset()
        self.status.set(f"已连接 {'FPGA PCIe' if pcie else '视频文件'}：{path}" +
                        (" · YOLO 已启用" if not isinstance(self.model, NoModelDetector) else " · 未加载检测模型"))

    def use_demo(self):
        if self.cap:
            self.cap.release()
            self.cap = None
        self.demo = True
        self.source_name = "demo"
        self.video_ended = False
        self.tracker = Tracker()
        self.lane.reset()
        self.status.set("演示模式 · 模拟目标，不代表实际识别")

    def demo_frame(self):
        f = np.full((540, 960, 3), (43, 50, 55), np.uint8)
        cv2.rectangle(f, (0, 0), (960, 250), (110, 96, 76), -1)
        cv2.line(f, (250, 539), (445, 250), (220, 220, 220), 4)
        cv2.line(f, (710, 539), (515, 250), (220, 220, 220), 4)
        for y in (310, 380, 470):
            cv2.line(f, (480, y), (480, y+30), (210, 210, 210), 3)
        return f

    def demo_detections(self):
        z = min(55, self.frame_count//7)
        return [Detection((415-z, 275-z//2, 550+z, 370+z), .94, "car"),
                Detection((665, 295, 760, 370), .88, "bus"),
                Detection((165, 335, 235, 400), .82, "motorbike")]

    def tick(self):
        tick_start = time.monotonic()
        now = time.monotonic()
        if self.demo:
            raw_frame = self.demo_frame()
            frame = self.process_weather(raw_frame)
            detections = self.demo_detections()
        elif self.video_ended:
            frame = np.zeros((540, 960, 3), dtype=np.uint8)
            raw_frame = frame
            cv2.putText(frame, "VIDEO ENDED", (350, 270), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
            detections = []
        else:
            ok, frame = self.cap.read() if self.cap else (False, None)
            if not ok:
                self.cap.release()
                self.cap = None
                self.video_ended = True
                self.tracker = Tracker()
                frame = np.zeros((540, 960, 3), dtype=np.uint8)
                raw_frame = frame
                cv2.putText(frame, "VIDEO ENDED / SOURCE LOST", (220, 270), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
                detections = []
                self.status.set("视频结束或视频源断流")
            else:
                raw_frame = cv2.resize(frame, (960, 540))
                frame = self.process_weather(raw_frame)
                self.video_frame += 1
                if not self.pcie:
                    position_s = self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                    now = position_s if np.isfinite(position_s) and position_s > 0 else self.video_frame/self.video_fps
                try:
                    detections = self.model.detect(frame, self.frame_count)
                except Exception as exc:
                    detections = []
                    self.status.set(f"推理失败：{exc}")
        try:
            targets = self.tracker.update(detections, now, self.ego.get(), self.focal.get(),
                                          self.reaction.get(), self.decel.get()) if self.enabled.get() else []
        except (ValueError, tk.TclError) as exc:
            targets = []
            self.status.set(f"参数无效：{exc}")
        lane_input = frame.copy()
        if self.weather_enabled.get() and not self.video_ended:
            blend = self.display_blend.get()/100
            frame = cv2.addWeighted(raw_frame, 1-blend, frame, blend, 0)
        hist_input = frame.copy()
        lane_debug = None
        lane_departure = None
        if self.lane_enabled.get() and not self.video_ended:
            self.apply_lane_controls()
            lane_result = self.lane.analyze(lane_input)
            lane_debug = lane_result
            lane_departure = lane_result.departure
            paint_lane_region(frame, lane_result)
            if lane_result.offset_fraction is None:
                for line in (lane_result.left, lane_result.right):
                    if line:
                        cv2.line(frame, (line[0], line[1]), (line[2], line[3]),
                                 (50, 255, 65), 3, cv2.LINE_AA)
            if lane_result.offset_fraction is not None:
                h, w = frame.shape[:2]
                cv2.line(frame, (w//2, h-1), (w//2, int(.83*h)), (245, 245, 245), 2)
                lane_center = int((lane_result.left[0] + lane_result.right[0]) / 2)
                cv2.arrowedLine(frame, (w//2, h-28), (lane_center, int(.83*h)),
                                (75, 230, 135), 3, cv2.LINE_AA, tipLength=.18)
                cv2.putText(frame, f"lane offset {lane_result.offset_fraction:+.2f}",
                            (20, h-20), cv2.FONT_HERSHEY_SIMPLEX, .65, (40, 225, 245), 2)
            lane_state = lane_result.departure or ("短时估计" if lane_result.held else
                                                   "正常" if lane_result.offset_fraction is not None else "不可用")
            self.metrics["车道状态"].config(text=lane_state,
                fg="#ff6e77" if lane_result.departure else GREEN)
            self.guidance.set(lane_result.assist + (" · 车道偏离警告" if lane_result.departure else ""))
        else:
            self.lane.reset()
            self.metrics["车道状态"].config(text="关闭" if not self.lane_enabled.get() else "--", fg=GREEN)
            self.guidance.set("车道保持辅助：未启用" if not self.lane_enabled.get() else "车道保持辅助：等待视频")
        for t in targets:
            x1, y1, x2, y2 = t.box
            color = COLORS[t.risk]
            cv2.rectangle(frame, (x1,y1), (x2,y2), color, 1 if t.stale else 2)
            speed = "--" if t.target_kmh is None else f"{t.target_kmh:.0f}km/h"
            line1 = f"#{t.id} {t.label}  {'TRACKING' if t.stale else speed}"
            line2 = f"last {t.distance_m:.1f}m" if t.stale else f"{t.distance_m:.1f}m  risk:{t.risk}"
            yy = max(22, y1-25)
            cv2.putText(frame, line1, (x1, yy), cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2)
            cv2.putText(frame, line2, (x1, yy+21), cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2)
        if self.demo:
            cv2.putText(frame, "DEMO / SIMULATED", (20, 38), cv2.FONT_HERSHEY_SIMPLEX, .75, (60, 190, 255), 2)
        if self.weather_enabled.get() and not self.video_ended:
            cv2.putText(frame, f"WEATHER {self.weather_strength.get()}%", (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, .65, (60, 220, 255), 2)
        fresh_targets = [t for t in targets if not t.stale]
        self.metrics["目标数"].config(text=str(len(targets)))
        self.metrics["最近目标"].config(text=f"{min(t.distance_m for t in fresh_targets):.1f} m" if fresh_targets else "--")
        levels = {"未就绪": 0, "低": 1, "中": 2, "高": 3}
        self.metrics["最高风险"].config(text=max((t.risk for t in fresh_targets), key=lambda x: levels[x], default="--"))
        if self.hist_enabled.get():
            if not self.histogram_panel.winfo_manager():
                self.histogram_panel.pack(after=self.visual_row, fill="x", pady=(0, 8))
            chart = render_histogram(hist_input)
            self.histogram_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(chart, cv2.COLOR_BGR2RGB)))
            self.histogram_view.config(image=self.histogram_photo)
        elif self.histogram_panel.winfo_manager():
            self.histogram_panel.pack_forget()
        danger = [t for t in fresh_targets if t.risk == "高"]
        if self.log_enabled.get() and not self.demo and not self.video_ended and (danger or lane_departure):
            details = {"source": self.source_name, "frame": self.video_frame,
                       "vehicle_risks": [{"id": t.id, "class": t.label,
                                          "distance_m": round(t.distance_m, 2)} for t in danger],
                       "lane_departure": lane_departure,
                       "weather": self.weather_mode.get() if self.weather_enabled.get() else "off"}
            try:
                saved = self.logger.record("danger", details, screenshot=frame, cooldown_key="danger")
                if saved:
                    self.status.set(f"危险画面已保存：{saved['image']}")
            except Exception as exc:
                self.status.set(f"日志保存失败：{exc}")
        wall_now = time.monotonic()
        self.metrics["帧率"].config(text=f"{1/max(.001, wall_now-self.last_time):.1f} FPS")
        self.last_time = wall_now
        mode = self.preview_mode.get()
        if lane_debug is not None and mode in ("二值图", "边缘图"):
            mask = lane_debug.binary if mode == "二值图" else lane_debug.edges
            shown = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            cv2.polylines(shown, lane_debug.roi_vertices, True, (255, 170, 55), 2)
            for line in (lane_debug.left, lane_debug.right):
                if line:
                    cv2.line(shown, (line[0], line[1]), (line[2], line[3]), (40, 225, 245), 3)
        else:
            shown = frame
            if lane_debug is not None:
                cv2.polylines(shown, lane_debug.roi_vertices, True, (150, 105, 55), 1)
        rgb = cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)
        view_w = max(1, self.preview.winfo_width())
        view_h = max(1, self.preview.winfo_height())
        scale = min(view_w/960, view_h/540)
        im = Image.fromarray(rgb).resize((max(1, int(960*scale)), max(1, int(540*scale))))
        self.photo = ImageTk.PhotoImage(im)
        self.preview.delete("frame")
        self.preview.create_image(view_w//2, view_h//2, image=self.photo, anchor="center", tags="frame")
        lane_text = ("偏离 " + lane_departure) if lane_departure else (
            "短时估计" if lane_debug is not None and lane_debug.held else
            "正常" if lane_debug is not None and lane_debug.offset_fraction is not None else "不可用")
        risk = max((t.risk for t in fresh_targets), key=lambda x: levels[x], default="--")
        closest = min((t.distance_m for t in fresh_targets), default=None)
        self.scene_summary.set(f"车辆 {len(fresh_targets)}   最高风险 {risk}\n"
                               f"车道 {lane_text}   最近 {'%.1f m' % closest if closest is not None else '--'}")
        road_w = max(120, self.road_preview.winfo_width())
        road_h = max(160, self.road_preview.winfo_height())
        scene = render_road_scene(road_w, road_h, lane_debug, targets)
        self.road_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(scene, cv2.COLOR_BGR2RGB)))
        self.road_preview.delete("all")
        self.road_preview.create_image(road_w//2, road_h//2, image=self.road_photo, anchor="center")
        self.frame_count += 1
        interval_ms = 50 if self.demo or self.pcie or self.video_ended else 1000/self.video_fps
        self.root.after(max(1, int(interval_ms - (time.monotonic()-tick_start)*1000)), self.tick)

    def close(self):
        if self.cap:
            self.cap.release()
        self.model.close()
        self.logger.record("session_end", {"source": self.source_name})
        self.root.destroy()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pcie-device", help="FPGA capture URL (/frame?cam=0 or 1) or V4L2 node")
    p.add_argument("--video", help="recorded video for development")
    p.add_argument("--model", help="RKNN Model Zoo optimized YOLOv8 model")
    p.add_argument("--pc-model", help="Ultralytics .pt model; yolov8n.pt downloads on first run")
    p.add_argument("--ego-kmh", type=float, default=40)
    p.add_argument("--focal-px", type=float, default=900)
    p.add_argument("--reaction-s", type=float, default=1.5)
    p.add_argument("--decel-mps2", type=float, default=4)
    p.add_argument("--weather-on", action="store_true", help="enable adverse-weather enhancement")
    p.add_argument("--weather-mode", choices=MODES, default="雾霾")
    p.add_argument("--weather-strength", type=int, default=50)
    p.add_argument("--log-dir", default=str(Path(__file__).resolve().parent / "logs"))
    p.add_argument("--log-max-mb", type=float, default=512)
    args = p.parse_args()
    root = tk.Tk()
    Dashboard(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
