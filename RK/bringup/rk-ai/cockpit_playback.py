"""Read TF/local clips independently of live capture and recording."""
from fractions import Fraction
from pathlib import Path
import ctypes
import hashlib
import json
import mmap
import os
import subprocess
import time

import cv2
import numpy as np
from cockpit_recorder import ordered_recordings, sd_directory
from four_camera_features import FIRST
from vision import NativeObjectDetector

WIDTH, HEIGHT = 1040, 584
FRAME_BYTES = WIDTH*HEIGHT*4
LOCAL = (Path("/home/linaro/Videos"),FIRST/"media")
EXTENSIONS = {".mp4",".mkv",".avi",".mov",".webm",".m4v"}


def update(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(value,encoding="utf-8")
    temp.replace(path)


def catalog(run):
    try:
        tf = list(reversed(ordered_recordings(sd_directory())))
        active=run/"record.active"
        if active.exists():
            prefix=f"sentry-{active.read_text(encoding='ascii')}-"
            current=max((p for p in tf if p.name.startswith(prefix)),default=None)
            tf=[p for p in tf if p!=current]
    except OSError:
        tf = []
    records = tf
    local = sorted({p for directory in LOCAL for p in directory.glob("*")
                    if p.is_file() and p.suffix.lower() in EXTENSIONS})
    files={}
    lines=[]
    for kind, paths in enumerate((records,local)):
        for path in paths:
            key=hashlib.sha256(os.fsencode(path)).hexdigest()[:16]
            files[key]=path,kind
            title=path.name.replace("\t"," ").replace("\n"," ")
            if kind==0:
                title=time.strftime("%m-%d %H:%M:%S",time.localtime(path.stat().st_mtime))+"  "+path.stem.split("-")[-1]
            lines.append(f"{kind}\t{key}\t{title}")
    update(run/"play.catalog","\n".join(lines)+"\n")
    return files


def probe(path):
    command=["ffprobe","-v","error","-select_streams","v:0",
             "-show_entries","format=duration:stream=avg_frame_rate,width,height","-of","json",str(path)]
    info=json.loads(subprocess.check_output(command,timeout=5))
    stream=info["streams"][0]
    fps=min(60,float(Fraction(stream["avg_frame_rate"])))
    if fps<=0:
        raise ValueError("invalid frame rate")
    return fps,float(info["format"].get("duration",0)),stream["width"],stream["height"]


class HardwareDecoder:
    def __init__(self,path,position,width,height):
        import gi
        gi.require_version("Gst","1.0")
        gi.require_version("GstVideo","1.0")
        from gi.repository import GLib,Gst,GstVideo
        Gst.init(None)
        self.gst,self.video=Gst,GstVideo
        scale=min(WIDTH/width,HEIGHT/height)
        self.width=max(2,int(width*scale/2+.5)*2)
        self.height=max(2,int(height*scale/2+.5)*2)
        self.canvas=np.zeros((HEIGHT,WIDTH,4),np.uint8)
        x,y=(WIDTH-self.width)//2,(HEIGHT-self.height)//2
        self.picture=self.canvas[y:y+self.height,x:x+self.width]
        try:
            self.pipeline=Gst.parse_launch(
                "uridecodebin name=src caps=video/x-raw expose-all-streams=false "
                "! appsink name=output sync=false max-buffers=2 enable-last-sample=false")
        except GLib.Error as error:
            raise OSError(str(error)) from error
        source=self.pipeline.get_by_name("src")
        self.sink=self.pipeline.get_by_name("output")
        self.mpp=False
        self.pipeline.connect("deep-element-added",self.configure)
        source.set_property("uri",path.resolve().as_uri())
        try:
            self.pipeline.set_state(Gst.State.PAUSED)
            status,_,_=self.pipeline.get_state(1500*Gst.MSECOND)
            if status!=Gst.StateChangeReturn.SUCCESS or not self.mpp:
                raise OSError("MPP decoder unavailable")
            if position and not self.pipeline.seek_simple(Gst.Format.TIME,
                    Gst.SeekFlags.FLUSH|Gst.SeekFlags.ACCURATE,int(position*Gst.SECOND)):
                raise OSError("MPP seek failed")
            self.pipeline.set_state(Gst.State.PLAYING)
        except Exception:
            self.close()
            raise

    def configure(self,_,__,element):
        factory=element.get_factory()
        if factory and factory.get_name()=="mppvideodec":
            self.mpp=True
            element.set_property("width",self.width)
            element.set_property("height",self.height)
            element.set_property("format",12)  # GstMppVideoDecFormat BGRA

    def read(self):
        sample=self.sink.emit("try-pull-sample",20*self.gst.MSECOND)
        if sample is None:
            bus=self.pipeline.get_bus()
            error=bus.pop_filtered(self.gst.MessageType.ERROR)
            if error:
                raise OSError(error.parse_error()[0].message)
            return b"" if self.sink.get_property("eos") else None
        caps=sample.get_caps().get_structure(0)
        if (caps.get_string("format"),caps.get_value("width"),caps.get_value("height"))!=(
                "BGRA",self.width,self.height):
            raise OSError("Unexpected MPP output")
        buffer=sample.get_buffer()
        size=buffer.get_size()
        data=buffer.extract_dup(0,size)
        meta=self.video.buffer_get_video_meta(buffer)
        stride=meta.stride[0] if meta else self.width*4
        start=meta.offset[0] if meta else 0
        if self.width==WIDTH and self.height==HEIGHT and stride==WIDTH*4:
            return data[start:start+FRAME_BYTES]
        pixels=np.ndarray((self.height,self.width,4),np.uint8,data,start,(stride,4,1))
        self.picture[:]=pixels
        return self.canvas.tobytes()

    def close(self):
        self.pipeline.set_state(self.gst.State.NULL)


class Playback:
    def __init__(self,run,detector):
        self.run,self.detector=run,detector
        self.cache=None
        self.process=None
        self.hardware=None
        self.key=""
        self.mode=0
        self.paused=False
        self.fps=self.duration=self.position=0.
        self.width=self.height=0
        self.boxes=[]
        self.next_infer=0.
        self.generation=0
        path=run/"play.frames"
        with path.open("wb+") as file:
            file.truncate(4+FRAME_BYTES)
            self.buffer=mmap.mmap(file.fileno(),0)
        self.address=ctypes.addressof(ctypes.c_char.from_buffer(self.buffer))
        self.pixels=np.ndarray((HEIGHT,WIDTH,4),np.uint8,self.buffer,offset=4)
        atomic=ctypes.CDLL("libatomic.so.1")
        self.store=getattr(atomic,"__atomic_store_4")
        self.store.argtypes=(ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int)
        self.sequence=0

    def status(self,state):
        update(self.run/"play.status",f"{self.key or '-'} {self.mode} {state} {self.position:.3f} "
               f"{self.duration:.3f} {self.fps:.2f} {self.width} {self.height}\n")

    def close(self):
        if self.hardware:
            self.hardware.close()
            self.hardware=None
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process.stdout.close()
            self.process=None

    @property
    def running(self):
        return self.hardware is not None or self.process is not None

    def software(self,path,position):
        self.process=subprocess.Popen(["ffmpeg","-nostdin","-v","error","-threads","2","-ss",str(position),
            "-i",str(path),"-an","-sn","-filter_threads","1","-vf",
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2",
            "-pix_fmt","bgra","-f","rawvideo","pipe:1"],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)

    def start(self,path,position):
        self.close()
        self.generation+=1
        self.cache=None
        self.position=position
        self.path=path
        self.paused=False
        self.boxes=[]
        self.next_infer=0.
        try:
            self.hardware=HardwareDecoder(path,position,self.width,self.height)
            print(f"Review video: MPP {self.width}x{self.height} {self.fps:.2f} fps",flush=True)
        except (ImportError,OSError,ValueError,RuntimeError):
            self.software(path,position)
        self.status(1)

    def command(self,cmd,files):
        action,*args=cmd.split()
        if action=="load" and args and args[0] in files:
            self.close()
            self.key=args[0]
            self.fps,self.duration,self.width,self.height=probe(files[self.key][0])
            self.start(files[self.key][0],0)
        if action=="pause" and self.running:
            self.paused=not self.paused
            self.status(2 if self.paused else 1)
        if action=="mode" and args in (["0"],["1"]):
            self.mode=int(args[0])
            self.generation+=1
            self.boxes=[]
            self.next_infer=0.
            if self.cache is not None:
                if self.mode and self.paused:
                    self.detector.submit(self.cache,self.generation)
                self.publish(self.cache)
            self.status(2 if self.paused else int(self.running))
        if action=="seek" and args and self.key in files and self.duration>0:
            self.start(files[self.key][0],self.duration*min(995,max(0,int(args[0])))/1000)
        if action=="stop":
            self.close()
            self.generation+=1
            self.paused=False
            self.key=""
            self.cache=None
            self.status(0)

    def publish(self,raw):
        self.sequence=(self.sequence+2)&0xfffffffe
        self.store(self.address,(self.sequence-1)&0xffffffff,5)
        self.buffer[4:]=raw
        if self.mode and self.boxes:
            for x,y,r,b,label in self.boxes:
                cv2.rectangle(self.pixels,(x,y),(r,b),(142,241,193,255),2)
                cv2.putText(self.pixels,label,(x,max(15,y-5)),cv2.FONT_HERSHEY_SIMPLEX,.53,(142,241,193,255),1,cv2.LINE_AA)
        self.store(self.address,self.sequence,5)

    def step(self,stamp):
        if self.hardware:
            try:
                raw=self.hardware.read()
            except (OSError,ValueError):
                self.close()
                self.software(self.path,self.position)
                return
            if raw is None:
                return
        else:
            raw=self.process.stdout.read(FRAME_BYTES)
        if len(raw)!=FRAME_BYTES:
            self.close()
            self.status(3)
            return
        self.cache=raw
        self.position+=1/self.fps
        if self.mode:
            if stamp>=self.next_infer:
                self.detector.submit(raw,self.generation)
                self.next_infer=stamp+.20
            self.boxes=self.detector.result(self.generation)
        self.publish(raw)


class ReviewDetector:
    """Separate latest-frame YOLO work so playback retains its source cadence."""
    def __init__(self,stop):
        import threading
        self.stop=stop
        self.pending=None
        self.output=(-1,[])
        self.event=threading.Event()
        self.thread=threading.Thread(target=self.run,name="review-yolo")
        self.thread.start()

    def submit(self,frame,generation):
        self.pending=frame,generation
        self.event.set()

    def result(self,generation):
        current,boxes=self.output
        return boxes if generation==current else []

    def run(self):
        model=None
        try:
            while not self.stop.is_set():
                if not self.event.wait(.2):
                    continue
                self.event.clear()
                if model is None:
                    model=NativeObjectDetector(FIRST/"rk_yolo_srv",FIRST/"yolov8n.rknn",0,
                                               classes={0:"person",2:"car",3:"motorbike",5:"bus",7:"truck",9:"traffic light"})
                frame_data,generation=self.pending
                pixels=np.frombuffer(frame_data,np.uint8).reshape(HEIGHT,WIDTH,4)
                frame=cv2.cvtColor(cv2.resize(pixels,(420,236)),cv2.COLOR_BGRA2BGR)
                self.output=generation,[(round(x*WIDTH/420),round(y*HEIGHT/236),round(r*WIDTH/420),
                              round(b*HEIGHT/236),f"{o.label} {o.score:.0%}")
                             for o in model.detect(frame) for x,y,r,b in (o.box,)]
        except (OSError,RuntimeError,cv2.error):
            self.output=(-1,[])
        finally:
            if model:
                model.close()


def playback_loop(run,stop):
    detector=ReviewDetector(stop)
    try:
        # Keep video buffer copies off the inference workers and the HDMI/DMA cores.
        os.sched_setaffinity(0,{4})
        os.setpriority(os.PRIO_PROCESS,0,-4)
    except OSError:
        pass
    player=Playback(run,detector)
    files={}
    cmd=run/"play.command"
    player.status(0)
    next_list=next_frame=next_status=0.
    try:
        while not stop.is_set():
            stamp=time.monotonic()
            if stamp>=next_list:
                try:
                    files=catalog(run)
                except OSError:
                    pass
                next_list=stamp+2
            try:
                # Rename before reading so a newer UI command remains available.
                current=run/"play.current"
                cmd.replace(current)
                command=current.read_text().strip()
                if command:
                    player.command(command,files)
                    next_frame=stamp
            except FileNotFoundError:
                pass
            except (OSError,ValueError,ZeroDivisionError,KeyError,IndexError,subprocess.SubprocessError):
                player.close()
                player.status(4)
            if player.running and not player.paused and stamp>=next_frame:
                player.step(stamp)
                next_frame+=1/player.fps
                if stamp-next_frame>.1:
                    next_frame=stamp+1/player.fps
                if player.running and stamp>=next_status:
                    player.status(1)
                    next_status=stamp+.25
            else:
                if player.paused and player.mode and player.cache is not None:
                    boxes=detector.result(player.generation)
                    if boxes!=player.boxes:
                        player.boxes=boxes
                        player.publish(player.cache)
                stop.wait(.003 if player.running and not player.paused else .05)
    finally:
        player.close()
        detector.thread.join(timeout=3)
