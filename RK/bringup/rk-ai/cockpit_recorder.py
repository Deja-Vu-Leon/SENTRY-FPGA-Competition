"""Hardware-encoded loop recording in a dedicated directory on the detected SD card."""
from pathlib import Path
import ctypes
import json
import mmap
import shutil
import time

import numpy as np


class RecordingFrames:
    def __init__(self,run):
        self.stride=4+420*236*4
        with (run/"record.frames").open("wb+") as file:
            file.truncate(4*self.stride)
            self.frames=mmap.mmap(file.fileno(),0)
        self.address=ctypes.addressof(ctypes.c_char.from_buffer(self.frames))
        self.load=getattr(ctypes.CDLL("libatomic.so.1"),"__atomic_load_4")
        self.load.argtypes=(ctypes.c_void_p,ctypes.c_int)
        self.load.restype=ctypes.c_uint32
        self.sequences=[0]*4
        self.latest=[None]*4

    def snapshot(self):
        stamp=time.monotonic()
        for index in range(4):
            offset=index*self.stride
            address=self.address+offset
            seq=self.load(address,5)
            if not seq or seq&1 or seq==self.sequences[index]:
                continue
            pixels=self.frames[offset+4:offset+self.stride]
            if seq==self.load(address,5):
                self.sequences[index]=seq
                self.latest[index]=(stamp,np.frombuffer(pixels,np.uint8).reshape(236,420,4)[:,:,:3])
        return self.latest


def sd_directory():
    for line in Path("/proc/self/mounts").read_text().splitlines():
        device, mount = line.split()[:2]
        if not device.startswith("/dev/mmcblk"):
            continue
        disk = Path(device).name.split("p")[0]
        kind = Path("/sys/class/block") / disk / "device/type"
        if kind.exists() and kind.read_text().strip() == "SD":
            directory = Path(mount.replace(r"\040", " ")) / "sentry-loop"
            directory.mkdir(exist_ok=True, mode=0o750)
            return directory
    raise OSError("找不到已挂载的 TF 卡")


ORDER_FILE = ".sentry-recording-order.json"


def recording_session(path):
    fields = path.stem.split("-")
    if len(fields) == 3 and fields[0] == "sentry" and fields[1].isdigit():
        return fields[1]
    return None


def recording_order(directory):
    try:
        value = json.loads((directory / ORDER_FILE).read_text(encoding="utf-8"))
        return [v for v in value if isinstance(v, str) and v.isdigit()] if isinstance(value, list) else []
    except (FileNotFoundError, ValueError):
        return []


def save_recording_order(directory, sessions):
    path = directory / ORDER_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sessions), encoding="utf-8")
    tmp.replace(path)


def ordered_recordings(directory):
    order = {session: i + 1 for i, session in enumerate(recording_order(directory))}
    entries = []
    for path in directory.glob("*.mp4"):
        try:
            attr = path.stat()
        except FileNotFoundError:
            continue
        session = recording_session(path)
        segment = path.stem.rsplit("-", 1)[-1]
        rank = order.get(session, 0)
        key = (rank, int(segment) if rank and segment.isdigit() else attr.st_mtime_ns, path.name)
        entries.append((key, path))
    return [path for _, path in sorted(entries)]


def prune(directory):
    segments = [path for path in ordered_recordings(directory) if recording_session(path)]
    sizes = [p.stat().st_size for p in segments]
    total = sum(sizes)
    while len(segments)>48 or total>2*1024**3 or shutil.disk_usage(directory).free<1024**3:
        if len(segments)<2:
            raise OSError("TF 卡可用空间不足")
        segments.pop(0).unlink()
        total-=sizes.pop(0)
    return len(segments)


def recording_status(run, state):
    tmp = run/"record.status.tmp"
    tmp.write_text(state, encoding="utf-8")
    tmp.replace(run/"record.status")


def record_loop(run, latest, stop):
    read_frames=latest if callable(latest) else lambda: tuple(latest)
    idle_status = "待机"
    recording_status(run, idle_status)
    while not stop.is_set():
        if not (run/"record.enabled").is_file():
            stop.wait(.5)
            continue
        pipeline = None
        try:
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst
            Gst.init(None)
            directory = sd_directory()
            prefix = time.time_ns()
            existing = {recording_session(path) for path in directory.glob("sentry-*.mp4")}
            while str(prefix) in existing:
                prefix += 1
            sessions = [session for session in recording_order(directory) if session in existing]
            save_recording_order(directory, [*sessions, str(prefix)])
            (run/"record.active").write_text(str(prefix),encoding="ascii")
            pipeline = Gst.parse_launch(
                "appsrc name=frames format=time is-live=true block=false max-buffers=2 leaky-type=downstream "
                "caps=video/x-raw,format=BGR,width=840,height=472,framerate=8/1 ! "
                "videoconvert ! video/x-raw,format=NV12 ! mpph264enc bps=2500000 gop=16 ! h264parse ! "
                "splitmuxsink name=segments max-size-time=15000000000 send-keyframe-requests=true"
            )
            source = pipeline.get_by_name("frames")
            pipeline.get_by_name("segments").set_property("location",str(directory/f"sentry-{prefix}-%05d.mp4"))
            if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise OSError("硬件编码器启动失败")
            bus = pipeline.get_bus()
            next_prune = 0
            frame_number = 0
            duration = Gst.SECOND // 8
            while not stop.is_set() and (run/"record.enabled").is_file():
                start = time.monotonic()
                message = bus.pop_filtered(Gst.MessageType.ERROR)
                if message:
                    raise OSError(str(message.parse_error()[0]))
                if start>=next_prune:
                    count = prune(directory)
                    recording_status(run, f"正在录像 · {count} 段")
                    next_prune = start+2
                canvas = np.zeros((472,840,3), np.uint8)
                for index, frame in enumerate(read_frames()):
                    if frame is not None and start-frame[0] < 1.5:
                        y,x = divmod(index,2)
                        canvas[y*236:(y+1)*236,x*420:(x+1)*420] = frame[1]
                buffer = Gst.Buffer.new_allocate(None,canvas.nbytes,None)
                buffer.fill(0,canvas.tobytes())
                buffer.pts = frame_number*duration
                buffer.duration = duration
                if source.emit("push-buffer",buffer) != Gst.FlowReturn.OK:
                    raise OSError("录像帧提交失败")
                frame_number += 1
                stop.wait(max(0,.125-(time.monotonic()-start)))
            recording_status(run, "正在保存最后一段录像…")
            source.emit("end-of-stream")
            final = bus.timed_pop_filtered(4*Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
            if not final or final.type != Gst.MessageType.EOS:
                raise OSError("录像分段结束失败")
            idle_status = "录像已保存 · 请查看 TF 卡历史"
        except Exception as exc:
            print(f"TF recording: {exc}", flush=True)
            idle_status = "录像暂停 · 检查 TF 卡与编码器"
            (run/"record.enabled").unlink(missing_ok=True)
        finally:
            if pipeline:
                pipeline.set_state(Gst.State.NULL)
            (run/"record.active").unlink(missing_ok=True)
            recording_status(run, idle_status)
