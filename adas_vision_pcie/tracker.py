"""Simple online association and illustrative monocular motion estimates."""
from dataclasses import dataclass
import math
import time


WIDTH_M = {"car": 1.8, "bus": 2.5, "truck": 2.5, "bike": .6, "motorbike": .8}


@dataclass
class Target:
    id: int
    label: str
    box: tuple[int, int, int, int]
    distance_m: float
    target_kmh: float | None
    closing_kmh: float | None
    ttc_s: float | None
    warning_distance_m: float | None
    risk: str
    age: int
    stale: bool = False


class Track:
    def __init__(self, id, det, distance, now):
        self.id, self.label, self.box = id, det.label, det.box
        self.distance = distance
        self.now = now
        self.closing_mps = None
        self.age = 1
        self.missed = 0
        self.class_votes = {det.label: max(.01, det.score)}


class Tracker:
    def __init__(self, max_missed_frames=6, max_hold_s=.35, box_alpha=.45,
                 new_track_conf=.35):
        self.tracks = []
        self.next_id = 1
        self.max_missed_frames = max_missed_frames
        self.max_hold_s = max_hold_s
        self.box_alpha = box_alpha
        self.new_track_conf = new_track_conf

    @staticmethod
    def _iou(a, b):
        x1, y1 = max(a[0], b[0]), max(a[1], b[1])
        x2, y2 = min(a[2], b[2]), min(a[3], b[3])
        intersection = max(0, x2-x1)*max(0, y2-y1)
        area_a = max(0,a[2]-a[0])*max(0,a[3]-a[1])
        area_b = max(0,b[2]-b[0])*max(0,b[3]-b[1])
        return intersection/max(1, area_a+area_b-intersection)

    def update(self, detections, now=None, ego_kmh=40, focal_px=900,
               reaction_s=1.5, decel_mps2=4.0, margin_m=3.0):
        if now is None:
            now = time.monotonic()
        if min(focal_px, reaction_s, decel_mps2) <= 0 or ego_kmh < 0 or margin_m < 0:
            raise ValueError("invalid settings")
        used = set()
        for det in detections:
            x1, y1, x2, y2 = det.box
            cx, cy = (x1+x2)/2, (y1+y2)/2
            candidates = []
            for tr in self.tracks:
                if (tr.id in used or tr.missed > self.max_missed_frames or
                        now-tr.now > self.max_hold_s):
                    continue
                a,b,c,e = tr.box
                ox, oy = (a+c)/2, (b+e)/2
                diagonal = max(40, math.hypot(c-a, e-b))
                gap = math.hypot(cx-ox, cy-oy)/diagonal
                overlap = self._iou(tr.box, det.box)
                # Class changes are allowed only for strongly overlapping boxes.
                if (tr.label == det.label and gap < 1.2) or (overlap >= .4 and gap < .6):
                    candidates.append((gap + (.2 if tr.label != det.label else 0), tr))
            if candidates:
                tr = min(candidates, key=lambda v: v[0])[1]
                smoothed = tuple(int(round((1-self.box_alpha)*old + self.box_alpha*new))
                                 for old, new in zip(tr.box, det.box))
                d = focal_px * WIDTH_M[tr.label] / max(1, smoothed[2]-smoothed[0])
                dt = now-tr.now
                if .015 <= dt <= 2.0:
                    observed = (tr.distance-d)/dt
                    # Reject implausibly large jumps from association or box jitter.
                    if abs(observed) <= 35:
                        tr.closing_mps = observed if tr.closing_mps is None else .75*tr.closing_mps+.25*observed
                for name in tuple(tr.class_votes):
                    tr.class_votes[name] *= .85
                tr.class_votes[det.label] = tr.class_votes.get(det.label, 0)+det.score
                new_label = max(tr.class_votes, key=tr.class_votes.get)
                if new_label != tr.label and tr.class_votes[new_label] > 1.3*tr.class_votes[tr.label]:
                    tr.label = new_label
                    d = focal_px * WIDTH_M[tr.label] / max(1, smoothed[2]-smoothed[0])
                    tr.closing_mps = None
                tr.box, tr.distance, tr.now = smoothed, d, now
                tr.age += 1
                tr.missed = 0
            else:
                if det.score < self.new_track_conf:
                    continue
                d = focal_px * WIDTH_M[det.label] / max(1, x2-x1)
                tr = Track(self.next_id, det, d, now)
                self.next_id += 1
                self.tracks.append(tr)
            used.add(tr.id)
        for tr in self.tracks:
            if tr.id not in used:
                tr.missed += 1
        self.tracks = [tr for tr in self.tracks if tr.missed <= self.max_missed_frames
                       and now-tr.now <= self.max_hold_s]
        results = []
        for tr in self.tracks:
            if tr.age < 2:
                continue
            stale = tr.missed > 0
            closing = max(0.0, tr.closing_mps) if tr.closing_mps is not None else None
            ttc = tr.distance/closing if closing is not None and closing > .1 else None
            warning_d = (closing*reaction_s + closing**2/(2*decel_mps2) + margin_m) if closing is not None else None
            risk = "暂失" if stale else "未就绪" if tr.age < 3 or closing is None else "高" if tr.distance <= warning_d else "中" if tr.distance <= 1.5*warning_d else "低"
            target_speed = (abs(ego_kmh - tr.closing_mps*3.6)
                            if tr.closing_mps is not None and not stale else None)
            results.append(Target(tr.id, tr.label, tr.box, tr.distance, target_speed,
                                  closing*3.6 if closing is not None else None,
                                  ttc, warning_d, risk, tr.age, stale))
        return results
