"""Track lane markings in replayed video, including already-rendered guides."""
from dataclasses import dataclass

import cv2

from cockpit_lane import cockpit_lane_analyzer
from green_lane import GreenLaneMonitor


@dataclass(frozen=True)
class VideoLaneResult:
    left: tuple | None
    right: tuple | None
    held: bool
    source: str


class VideoLaneAnalyzer:
    def __init__(self):
        self.paint = cockpit_lane_analyzer()
        self.guides = GreenLaneMonitor()
        self.previous = None
        self.timestamp = None

    def reset(self):
        self.paint.reset()
        self.guides = GreenLaneMonitor()
        self.previous = self.timestamp = None

    def analyze(self, frame, stamp):
        thumbnail = cv2.resize(frame,(40,24),interpolation=cv2.INTER_AREA)
        if self.timestamp is not None and (stamp<self.timestamp or stamp-self.timestamp>1.0
                or cv2.mean(cv2.absdiff(thumbnail,self.previous))[1]>42):
            self.reset()
        self.previous, self.timestamp = thumbnail, stamp
        left, right = self.guides.update(frame,stamp)
        if left or right:
            self.paint.reset()
            width, height = frame.shape[1]-1, frame.shape[0]-1
            def pixels(line):
                if not line:
                    return None
                a,b = line.near
                c,d = line.far
                return round(a*width),round(b*height),round(c*width),round(d*height)
            return VideoLaneResult(pixels(left),pixels(right),False,"guide")
        result = self.paint.analyze(frame)
        return VideoLaneResult(result.left,result.right,result.held,"paint")
