"""Offline, CPU-bounded inference for Ultralytics road and slope models."""
from collections import deque
from dataclasses import dataclass
import os
from pathlib import Path
import sys
import threading
import time

import cv2
import numpy as np

CRACKS = ("D00","D10","D20","D40")
SLOPE = ("landslide debris","landslide scar")
CRACK_MODEL = "rdd_yolo12n_640.onnx",640
CRACK_THRESHOLDS = (.25,.45,.40,.25)
SLOPE_MODEL = "landslide_320.onnx",320
SLOPE_BOX_MODEL = "landslide_320_boxes.onnx",320
SLOPE_THRESHOLDS = (.35,.35)
bundled_runtime = Path(__file__).resolve().with_name("hazard_runtime")
if bundled_runtime.is_dir():
    sys.path.insert(0,str(bundled_runtime))


@dataclass
class Hazard:
    kind: int
    score: float
    box: tuple
    mask: np.ndarray | None = None


def box_iou(a, b):
    x = max(0,min(a[2],b[2])-max(a[0],b[0]))
    y = max(0,min(a[3],b[3])-max(a[1],b[1]))
    area = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])
    return x*y/max(1,area-x*y)


class HazardModel:
    def __init__(self, file, size, classes, threshold, masks=False):
        self.size, self.classes, self.masks = size,classes,masks
        self.threshold = np.broadcast_to(np.asarray(threshold,dtype=np.float32),(len(classes),))
        try:
            import onnxruntime as ort
        except ImportError:
            self.net = cv2.dnn.readNetFromONNX(str(file))
            self.session = None
        else:
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 1
            self.session = ort.InferenceSession(str(file), opts, providers=["CPUExecutionProvider"])
            self.input = self.session.get_inputs()[0].name

    def detect(self, frame, return_masks=False):
        height,width = frame.shape[:2]
        ratio = min(self.size/width,self.size/height)
        w,h = round(width*ratio),round(height*ratio)
        x,y = (self.size-w)//2,(self.size-h)//2
        canvas = np.full((self.size,self.size,3),114,np.uint8)
        canvas[y:y+h,x:x+w] = cv2.resize(frame,(w,h),interpolation=cv2.INTER_LINEAR)
        blob = cv2.dnn.blobFromImage(canvas,1/255.,swapRB=True)
        if self.session:
            output = self.session.run(None,{self.input:blob})
        else:
            self.net.setInput(blob)
            output = self.net.forward(self.net.getUnconnectedOutLayersNames())
        rows = next(a[0].T for a in output if a.ndim==3)
        class_scores = rows[:,4:4+len(self.classes)]
        class_ids = np.argmax(class_scores,axis=1)
        scores = np.max(class_scores,axis=1)
        found = []
        for value in np.flatnonzero(scores>=self.threshold[class_ids]):
            cx,cy,bw,bh = map(float,rows[value,:4])
            box = tuple(map(round,((cx-bw/2-x)/ratio,(cy-bh/2-y)/ratio,
                                   (cx+bw/2-x)/ratio,(cy+bh/2-y)/ratio)))
            box = tuple(max(0,min(n,limit)) for n,limit in zip(box,(width-1,height-1,width-1,height-1)))
            if box[0]<box[2] and box[1]<box[3]:
                found.append((int(value),Hazard(int(class_ids[value]),float(scores[value]),box)))
        kept = []
        for value, hit in sorted(found,key=lambda item:item[1].score,reverse=True):
            if any(hit.kind==old.kind and box_iou(hit.box,old.box)>.45 for old in kept):
                continue
            if return_masks and self.masks:
                basis = next(a[0] for a in output if a.ndim==4)
                coeff = rows[value,4+len(self.classes):]
                mask = (coeff @ basis.reshape(basis.shape[0],-1)).reshape(basis.shape[1:])
                mask = cv2.resize(mask,(self.size,self.size))[y:y+h,x:x+w]
                mask = cv2.resize(mask,(width,height)) > 0
                x1,y1,x2,y2 = hit.box
                hit.mask = np.zeros(mask.shape,bool)
                hit.mask[y1:y2,x1:x2] = mask[y1:y2,x1:x2]
            kept.append(hit)
            if len(kept)>=12:
                break
        return kept


class CorroboratedCracks:
    """Use a reflected view to verify borderline crack boxes."""
    low = (.20,.30,.35)
    reflected_min = (.25,.50,.40)

    def __init__(self, model):
        self.model = model

    def detect(self, frame):
        candidates = [x for x in self.model.detect(frame) if x.kind<3]
        weak = [x for x in candidates if x.score<CRACK_THRESHOLDS[x.kind]]
        confirmed = [x for x in candidates if x.score>=CRACK_THRESHOLDS[x.kind]]
        if not weak:
            return confirmed
        width = frame.shape[1]-1
        reflected = self.model.detect(cv2.flip(frame,1))
        for hit in weak:
            if any(other.kind==hit.kind and other.score>=self.reflected_min[hit.kind] and
                   box_iou(hit.box,(width-other.box[2],other.box[1],width-other.box[0],other.box[3]))>=.60
                   for other in reflected):
                confirmed.append(hit)
        return sorted(confirmed,key=lambda hit:hit.score,reverse=True)


class PersistentHazards:
    def __init__(self, model, interval, accepted):
        self.model, self.interval, self.accepted = model,interval,accepted
        self.history = deque(maxlen=2)
        self.confirmed = []
        self.last_stamp = None
        self.previous_frame = None
        self.previous_stamp = None
        self.inference_seconds = 0

    def update(self, frame, stamp, detail=None):
        thumbnail = cv2.resize(frame,(32,18),interpolation=cv2.INTER_AREA)
        if self.previous_frame is not None and (
            not 0<=stamp-self.previous_stamp<=max(1.0,self.inference_seconds+.8) or
            max(cv2.mean(cv2.absdiff(thumbnail,self.previous_frame))[:3])>42
        ):
            self.history.clear()
            self.confirmed = []
            self.last_stamp = None
        self.previous_frame,self.previous_stamp = thumbnail,stamp
        if self.last_stamp is not None:
            elapsed = stamp-self.last_stamp
            if elapsed<self.interval:
                return self.confirmed
        max_history_age = 2.5*max(self.interval,self.inference_seconds+.1)
        while self.history and stamp-self.history[0][0]>max_history_age:
            self.history.popleft()
        source = detail() if detail else None
        if source is None:
            source = frame
        start = time.monotonic()
        current = [x for x in self.model.detect(source) if x.kind in self.accepted]
        self.inference_seconds = time.monotonic()-start
        if source.shape[:2]!=frame.shape[:2]:
            x_ratio,y_ratio = frame.shape[1]/source.shape[1],frame.shape[0]/source.shape[0]
            right,bottom = frame.shape[1]-1,frame.shape[0]-1
            for hit in current:
                hit.box = tuple(min(limit,round(coordinate*ratio)) for coordinate,ratio,limit in
                                zip(hit.box,(x_ratio,y_ratio,x_ratio,y_ratio),(right,bottom,right,bottom)))
            current = [x for x in current if x.box[0]<x.box[2] and x.box[1]<x.box[3]]
        self.confirmed = [x for x in current if any(
            x.kind==old.kind and box_iou(x.box,old.box)>.25
            for _, previous in self.history for old in previous
        )]
        self.history.append((stamp,current))
        self.last_stamp = stamp
        return self.confirmed


class LatestHazards:
    """Keep heavy hazard inference away from capture, recording and pedestrian inference."""
    def __init__(self, tracker, cpu=None):
        self.tracker = tracker
        self.cpu = cpu
        self.ready = threading.Condition()
        self.pending = None
        self.output = None
        self.failure = None
        self.closed = False
        self.thread = threading.Thread(target=self.run,name="hazard-inference")
        self.thread.start()

    def run(self):
        if self.cpu is not None:
            try:
                os.sched_setaffinity(0,{self.cpu})
            except (AttributeError,OSError) as exc:
                print(f"Hazard inference CPU {self.cpu} unavailable: {exc}",flush=True)
        try:
            while True:
                with self.ready:
                    self.ready.wait_for(lambda:self.closed or self.pending is not None)
                    if self.closed:
                        return
                    frame,stamp,detail = self.pending
                    self.pending = None
                hits = self.tracker.update(frame,stamp,detail)
                anchor = self.tracker.previous_frame
                expires = time.monotonic()+max(1.0,self.tracker.inference_seconds+.25)
                with self.ready:
                    self.output = hits,anchor,expires
        except Exception as exc:
            with self.ready:
                self.failure = exc

    def update(self, frame, stamp, detail):
        with self.ready:
            if self.failure:
                raise RuntimeError("hazard inference worker failed") from self.failure
            self.pending = frame,stamp,detail
            self.ready.notify()
            output = self.output
        if output is None or stamp>output[2] or not output[0]:
            return []
        thumb = cv2.resize(frame,(32,18),interpolation=cv2.INTER_AREA)
        if max(cv2.mean(cv2.absdiff(thumb,output[1]))[:3])>42:
            return []
        return output[0]

    def close(self):
        with self.ready:
            self.closed = True
            self.ready.notify()
        self.thread.join()
