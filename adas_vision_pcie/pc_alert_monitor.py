"""Windows SENTRY monitor for RK high-risk snapshots and event logs."""

import argparse
import csv
from datetime import datetime
import io
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import shutil
import socket
import subprocess
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler

from PIL import Image, ImageTk


FIELDS = ("received_at", "captured_at_utc", "channel", "source", "reason", "distance_m",
          "closing_kmh", "speed_kmh", "ttc_s", "image", "id")
SAFE_ID = re.compile(r"[0-9a-f]{32}\Z")
BG, CARD, DARK = "#0b111d", "#121d2c", "#060c15"
TEXT, MUTED, EDGE = "#ecf3fb", "#a7bbce", "#26374b"
GOLD, RED, GREEN = "#ffd054", "#ff7880", "#75deb1"


class LocalLog:
    def __init__(self, directory):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def entries(self):
        for path in self.directory.glob("*.json"):
            try:
                event = json.loads(path.read_text(encoding="utf-8"))
                if (SAFE_ID.fullmatch(event["id"]) and event["id"] == path.stem and
                        (self.directory / (path.stem + ".jpg")).is_file()):
                    yield event
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def has(self, key):
        return (self.directory / (key + ".json")).is_file() and (self.directory / (key + ".jpg")).is_file()

    def save(self, event, jpeg):
        key = event["id"]
        if not SAFE_ID.fullmatch(key):
            raise ValueError("Invalid event ID")
        with Image.open(io.BytesIO(jpeg)) as image:
            if image.format != "JPEG":
                raise ValueError("Invalid event image")
            image.verify()
        record = {field: event.get(field) for field in FIELDS}
        record.update(received_at=datetime.now().astimezone().isoformat(timespec="seconds"), image=key + ".jpg")
        for suffix, data in ((".jpg", jpeg), (".json", json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"))):
            path = self.directory / (key + suffix)
            temp = path.with_suffix(suffix + ".tmp")
            temp.write_bytes(data)
            temp.replace(path)
        return record

    def export(self):
        dest = self.directory / f"危险事件_{datetime.now():%Y%m%d_%H%M%S_%f}.csv"
        with dest.open("w", newline="", encoding="utf-8-sig") as stream:
            out = csv.DictWriter(stream, fieldnames=FIELDS)
            out.writeheader()
            out.writerows(sorted(self.entries(), key=lambda event: event["received_at"]))
        return dest


class AlertClient:
    def __init__(self, args, logs, inbox):
        self.args, self.logs, self.inbox = args, logs, inbox
        self.stop = Event()
        self.thread = Thread(target=self.run, daemon=True)
        self.cursor = 0
        self.source_id = None
        self.status = None
        self.opener = build_opener(ProxyHandler({}))

    def post_status(self, connected, detail):
        value = connected, detail
        if value != self.status:
            self.status = value
            self.inbox.put(("status", value))

    def tunnel(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        ssh = shutil.which("ssh")
        if ssh is None:
            raise OSError("Windows 找不到 OpenSSH 客户端")
        command = [ssh, "-N", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                   "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=4",
                   "-o", "ServerAliveInterval=4", "-o", "ServerAliveCountMax=2"]
        if self.args.ssh_key is not None:
            if not self.args.ssh_key.is_file():
                raise OSError("找不到 RK 的 SSH 密钥")
            command += ["-o", "IdentitiesOnly=yes", "-i", str(self.args.ssh_key)]
        command += ["-L", f"127.0.0.1:{port}:127.0.0.1:{self.args.remote_port}", self.args.host]
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return proc, f"http://127.0.0.1:{port}"

    def get(self, endpoint, path, max_bytes):
        with self.opener.open(endpoint + path, timeout=2.5) as response:
            body = response.read(max_bytes+1)
        if len(body) > max_bytes:
            raise ValueError("Event response too large")
        return body

    def poll(self, endpoint):
        data = json.loads(self.get(endpoint, f"/events?after={self.cursor}", 128*1024))
        if self.source_id is not None and self.source_id != data["source_id"]:
            self.cursor = 0
            data = json.loads(self.get(endpoint, "/events?after=0", 128*1024))
        self.source_id = data["source_id"]
        for event in data["events"]:
            if self.stop.is_set():
                break
            seq, key = int(event["seq"]), event["id"]
            if event.get("level") == "high" and SAFE_ID.fullmatch(key) and not self.logs.has(key):
                try:
                    jpg = self.get(endpoint, f"/image/{seq}", 4*1024*1024)
                except HTTPError as exc:
                    if exc.code != 404:
                        raise
                else:
                    self.inbox.put(("event", self.logs.save(event, jpg)))
            self.cursor = max(self.cursor, seq)
        return len(data["events"])

    def run(self):
        proc, endpoint = None, self.args.endpoint
        try:
            while not self.stop.is_set():
                try:
                    if not self.args.endpoint and (proc is None or proc.poll() is not None):
                        self.post_status(False, "正在连接 RK · " + self.args.host)
                        proc, endpoint = self.tunnel()
                        self.stop.wait(.7)
                    count = self.poll(endpoint)
                    self.post_status(True, "RK 预警已连接")
                    self.stop.wait(.08 if count == 40 else .8)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    if isinstance(exc, (PermissionError, FileNotFoundError)):
                        detail = "无法保存日志 · " + str(exc)
                    else:
                        detail = "连接或写入暂不可用 · 正在重试"
                    self.post_status(False, detail)
                    self.stop.wait(2)
        finally:
            self.stop.set()
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()


def short_time(value):
    return (value or "—").replace("T", " ")[:19]


def num(value, unit, *, signed=False):
    if not isinstance(value, (int, float)):
        return "—"
    return (f"{value:+.1f}" if signed else f"{value:.1f}") + f" {unit}"


class Monitor:
    def __init__(self, root, args):
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.root, self.tk, self.ttk, self.messagebox = root, tk, ttk, messagebox
        self.logs = LocalLog(args.log_dir)
        self.inbox = Queue()
        self.entries = {}
        self.selected = self.latest = self.image = self.photo = self.redraw_timer = None
        self.follow = tk.BooleanVar(value=True)
        root.title("SENTRY / 危险事件监看")
        root.geometry("1230x760")
        root.minsize(880, 560)
        root.configure(bg=BG)
        self.build()
        for event in sorted(self.logs.entries(), key=lambda e: e["received_at"])[-400:]:
            self.add(event, follow=False)
        self.go_latest()
        self.client = AlertClient(args, self.logs, self.inbox)
        self.client.thread.start()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(80, self.refresh)

    def label(self, parent, text, size=10, *, fg=TEXT, bg=CARD, bold=False, **kwargs):
        return self.tk.Label(parent, text=text, fg=fg, bg=bg, font=("Microsoft YaHei UI", size,
                             "bold" if bold else "normal"), **kwargs)

    def build(self):
        tk, ttk = self.tk, self.ttk
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Alert.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                        rowheight=32, borderwidth=0, font=("Microsoft YaHei UI", 10))
        style.configure("Alert.Treeview.Heading", background=EDGE, foreground=TEXT, relief="flat",
                        font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Alert.Treeview", background=[("selected", "#324b64")], foreground=[("selected", "#ffffff")])

        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=22, pady=(18, 12))
        self.label(top, "SENTRY", 22, fg=GOLD, bg=BG, bold=True).pack(side="left")
        self.label(top, "危险事件监看", 15, bg=BG, bold=True).pack(side="left", padx=14)
        self.connection = self.label(top, "连接中…", 10, fg=GOLD, bg=BG)
        self.connection.pack(side="right")
        body = tk.PanedWindow(self.root, bg=BG, sashwidth=9, borderwidth=0, opaqueresize=True)
        body.pack(fill="both", expand=True, padx=22)
        preview = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=EDGE)
        history = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=EDGE)
        body.add(preview, minsize=500, stretch="always")
        body.add(history, minsize=300, width=340, stretch="never")
        self.headline = self.label(preview, "等待危险画面", 15, bold=True, anchor="w")
        self.headline.pack(fill="x", padx=16, pady=(13, 2))
        self.subhead = self.label(preview, "RK 触发红色预警后自动显示抓拍", fg=MUTED, anchor="w")
        self.subhead.pack(fill="x", padx=16, pady=(0, 10))
        self.canvas = tk.Canvas(preview, bg=DARK, highlightthickness=0, width=1, height=1)
        self.canvas.pack(fill="both", expand=True, padx=12)
        self.canvas.bind("<Configure>", self.schedule_draw)
        facts = tk.Frame(preview, bg=CARD)
        facts.pack(fill="x", padx=12, pady=12)
        self.fact_values = []
        for i, title in enumerate(("估算距离", "相对速度", "预计接近时间", "同向参考车速")):
            facts.columnconfigure(i, weight=1, uniform="facts")
            tile = tk.Frame(facts, bg=DARK)
            tile.grid(row=0, column=i, sticky="ew", padx=3)
            self.label(tile, title, 9, fg=MUTED, bg=DARK).pack(pady=(6, 0))
            value = self.label(tile, "—", 14, fg=GOLD, bg=DARK, bold=True)
            value.pack(pady=(1, 7))
            self.fact_values.append(value)

        self.label(history, "事件日志", 14, bold=True).pack(anchor="w", padx=14, pady=(12, 4))
        tk.Checkbutton(history, text="跟随最新事件", variable=self.follow, command=self.go_latest,
                       bg=CARD, fg=TEXT, selectcolor=DARK, activebackground=CARD, activeforeground=TEXT,
                       font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=12, pady=(0, 5))
        table = tk.Frame(history, bg=CARD)
        table.pack(fill="both", expand=True, padx=10, pady=(0, 12))
        self.tree = ttk.Treeview(table, style="Alert.Treeview", columns=("time", "camera", "reason"),
                                 show="headings", selectmode="browse")
        for col, title, width in (("time", "接收时间", 112), ("camera", "通道", 55), ("reason", "触发原因", 118)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, minwidth=52, anchor="center")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<ButtonRelease-1>", self.on_click)

        foot = tk.Frame(self.root, bg=BG)
        foot.pack(fill="x", padx=22, pady=12)
        self.footer = self.label(foot, "每条事件保存 JPEG 画面和 JSON 日志", 9, fg=MUTED, bg=BG)
        self.footer.pack(side="left")
        ttk.Button(foot, text="打开日志文件夹", command=self.open_logs).pack(side="right")
        ttk.Button(foot, text="导出 CSV", command=self.export).pack(side="right", padx=8)

    def add(self, event, *, follow=True):
        key = event["id"]
        if key in self.entries:
            return
        self.latest = key
        self.entries[key] = event
        self.tree.insert("", 0, iid=key, values=(short_time(event["received_at"])[11:],
                         f"CH {event['channel']:02}", event["reason"]))
        if len(self.entries) > 400:
            oldest = self.tree.get_children()[-1]
            self.tree.delete(oldest)
            del self.entries[oldest]
        if follow:
            self.go_latest()

    def go_latest(self):
        if self.follow.get() and self.latest:
            self.tree.selection_set(self.latest)
            self.tree.see(self.latest)
            self.show(self.latest)

    def on_select(self, _event):
        chosen = self.tree.selection()
        if chosen:
            self.show(chosen[0])

    def on_click(self, event):
        key = self.tree.identify_row(event.y)
        if key and key != self.latest:
            self.follow.set(False)

    def show(self, key):
        if key == self.selected or key not in self.entries:
            return
        self.selected = key
        entry = self.entries[key]
        try:
            with Image.open(self.logs.directory / (key + ".jpg")) as image:
                self.image = image.convert("RGB")
        except OSError:
            self.image = None
        source = "实时" if entry.get("source") == "live" else "录播"
        self.headline.configure(text=f"危险抓拍 · {entry['reason']}", fg=RED)
        self.subhead.configure(text=f"CH {entry['channel']:02} · {source}    接收于 {short_time(entry['received_at'])}")
        for widget, field, unit in zip(self.fact_values, ("distance_m", "closing_kmh", "ttc_s", "speed_kmh"),
                                       ("m", "km/h", "s", "km/h")):
            widget.configure(text=num(entry.get(field), unit, signed=field == "closing_kmh"))
        self.schedule_draw()

    def schedule_draw(self, _event=None):
        if self.redraw_timer is None:
            self.redraw_timer = self.root.after(45, self.draw)

    def draw(self):
        self.redraw_timer = None
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.canvas.delete("all")
        if self.image is None:
            self.canvas.create_text(w//2, h//2, text="等待事件截图" if not self.selected else "截图不可用",
                                    fill=MUTED, font=("Microsoft YaHei UI", 13))
            return
        size = min(w/self.image.width, h/self.image.height)
        fit = (max(1, round(self.image.width*size)), max(1, round(self.image.height*size)))
        self.photo = ImageTk.PhotoImage(self.image.resize(fit, Image.Resampling.BILINEAR), master=self.canvas)
        self.canvas.create_image(w//2, h//2, image=self.photo)

    def refresh(self):
        for _ in range(30):
            try:
                kind, data = self.inbox.get_nowait()
            except Empty:
                break
            if kind == "status":
                connected, detail = data
                self.connection.configure(text=("●  " if connected else "○  ") + detail,
                                          fg=GREEN if connected else GOLD)
            else:
                self.add(data)
        self.root.after(100, self.refresh)

    def open_logs(self):
        if hasattr(os, "startfile"):
            os.startfile(self.logs.directory)
        else:
            subprocess.Popen(["xdg-open", str(self.logs.directory)])

    def export(self):
        try:
            path = self.logs.export()
            self.footer.configure(text=f"已导出 {path.name}")
        except OSError as exc:
            self.messagebox.showerror("导出失败", str(exc), parent=self.root)

    def close(self):
        self.client.stop.set()
        self.root.destroy()


def main():
    import tkinter as tk

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="RK SSH target, e.g. linaro@rk3576.local")
    parser.add_argument("--ssh-key", type=Path)
    parser.add_argument("--remote-port", type=int, default=8791)
    parser.add_argument("--endpoint", help="use a manually forwarded loopback endpoint")
    parser.add_argument("--log-dir", type=Path, default=Path.home() / "Desktop" / "SENTRY 危险事件日志")
    args = parser.parse_args()
    root = tk.Tk()
    monitor = Monitor(root, args)
    try:
        root.mainloop()
    finally:
        monitor.client.stop.set()
        monitor.client.thread.join(timeout=4)


if __name__ == "__main__":
    main()
