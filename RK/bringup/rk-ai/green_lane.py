"""Find the narrow green guides baked into the HDMI demo material."""

from dataclasses import dataclass
from math import hypot

import cv2
import numpy as np


@dataclass(frozen=True)
class GreenLine:
    far: tuple[float, float]
    near: tuple[float, float]


def find_green_lanes(frame):
    h, w = frame.shape[:2]
    top, end = round(.57*h), round(.986*h)
    if end - top < 16:
        return None, None
    road = frame[top:end]
    hsv = cv2.cvtColor(road, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (31, 34, 154), (94, 255, 255))
    blue, green, red = cv2.split(road)
    mask &= cv2.inRange(cv2.subtract(green, red), 16, 255)
    mask &= cv2.inRange(cv2.subtract(green, blue), 8, 255)
    if cv2.countNonZero(mask) < max(10, w//30):
        return None, None
    connected = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    lines = cv2.HoughLinesP(connected, 1, np.pi/180, threshold=max(7, w//55),
                           minLineLength=max(10, w//40), maxLineGap=max(3, w//68))
    if lines is None:
        return None, None
    best = [None, None]
    scores = [0., 0.]
    for x0, y0, x1, y1 in lines.reshape(-1, 4):
        if y1 < y0:
            x0, y0, x1, y1 = x1, y1, x0, y0
        dy = int(y1-y0)
        if dy < max(6, round(.024*h)) or top+y1 < .73*h:
            continue
        slope = float(x1-x0)/dy
        if not .28 <= abs(slope) <= 4.1:
            continue
        side = int(slope > 0)
        near_x = (x0 + slope*(.91*h-top-y0))/w
        far_x = (x0 + slope*(.61*h-top-y0))/w
        if side == 0 and not (.02 <= near_x <= .49 and .22 <= far_x <= .66):
            continue
        if side == 1 and not (.51 <= near_x <= 1.04 and .32 <= far_x <= .79):
            continue
        ys = np.arange(y0, y1+1, dtype=np.intp)
        xs = np.rint(x0 + slope*(ys-y0)).astype(np.intp)
        edge = max(5, w//78)
        valid = (xs >= edge) & (xs < w-edge)
        if np.count_nonzero(valid) < 6:
            continue
        ys, xs = ys[valid], xs[valid]
        center = np.maximum.reduce([mask[ys, xs+j] for j in (-1, 0, 1)]) > 0
        flanks = ((mask[ys, xs-edge] > 0).mean() + (mask[ys, xs+edge] > 0).mean())/2
        coverage = center.mean()
        if coverage < .55 or flanks > .36:
            continue
        score = hypot(int(x1-x0), dy)*coverage*(1-flanks)
        if score > scores[side]:
            scores[side] = score
            best[side] = GreenLine((x0/(w-1), (top+y0)/(h-1)),
                                   (x1/(w-1), (top+y1)/(h-1)))
    left, right = best
    if left is not None and right is not None and left.near[0] >= right.near[0]-.04:
        best[0 if scores[0] < scores[1] else 1] = None
    return tuple(best)


def _x_at(line, y):
    return line.far[0] + (line.near[0]-line.far[0]) * (y-line.far[1])/(line.near[1]-line.far[1])


def _coherent(a, b):
    return abs(_x_at(a, .84) - _x_at(b, .84)) <= .065


class GreenLaneMonitor:
    def __init__(self):
        self.sampled_at = None
        self.pending = [None, None]
        self.confirmed = [None, None]
        self.seen_at = [None, None]

    def update(self, frame, now):
        if self.sampled_at is not None and now < self.sampled_at:
            self.__init__()
        if self.sampled_at is not None and now - self.sampled_at < .10:
            return tuple(self.confirmed)
        self.sampled_at = now
        for i, line in enumerate(find_green_lanes(frame)):
            old = self.pending[i]
            if line is not None and old is not None and _coherent(line, old):
                def smooth(current, previous):
                    return tuple(.60*a + .40*b for a, b in zip(current, previous))
                self.confirmed[i] = GreenLine(smooth(line.far, old.far), smooth(line.near, old.near))
                self.seen_at[i] = now
            elif self.seen_at[i] is not None and now-self.seen_at[i] > .30:
                self.confirmed[i] = None
                self.seen_at[i] = None
            self.pending[i] = line
        return tuple(self.confirmed)
