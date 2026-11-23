"""Experimental lane marking extraction and advisory lane-centering cues."""
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class LaneResult:
    left: tuple[int, int, int, int] | None
    right: tuple[int, int, int, int] | None
    offset_fraction: float | None
    departure: str | None
    assist: str
    confidence: float
    binary: np.ndarray
    edges: np.ndarray
    roi_vertices: np.ndarray
    held: bool = False


class LaneAnalyzer:
    def __init__(self, camera_center_ratio=.5, departure_threshold=.22, consecutive=3):
        self.camera_center_ratio = camera_center_ratio
        self.departure_threshold = departure_threshold
        self.consecutive = consecutive
        self.previous = None
        self.last_valid = None
        self.missing = 0
        self.hold_frames = 6
        self.left_count = 0
        self.right_count = 0
        self.white_min = 155
        self.canny_low = 60
        self.canny_high = 160
        self.roi_top_pct = 55
        self.roi_center_ratio = .5
        self.roi_top_half_pct = 10
        self.roi_bottom_half_pct = 44
        self.hough_votes = 35
        self.min_line_pct = 6
        self.local_contrast = False
        self.crop_to_roi = False
        self.stable_fit = False
        self.side_lines = [None, None]
        self.side_hits = [0, 0]

    def reset(self):
        self.previous = None
        self.last_valid = None
        self.missing = 0
        self.left_count = self.right_count = 0
        self.side_lines = [None, None]
        self.side_hits = [0, 0]

    def _missing_result(self, left, right, binary, edges, vertices, confidence=0.):
        self.missing += 1
        self.left_count = self.right_count = 0
        if self.last_valid is not None and self.missing <= self.hold_frames:
            old = self.last_valid
            return LaneResult(old.left, old.right, old.offset_fraction, None,
                              "短时保持上次车道估计", old.confidence * (1-self.missing/(self.hold_frames+1)),
                              binary, edges, vertices, held=True)
        if self.stable_fit:
            self.previous = self.last_valid = None
        else:
            self.reset()
        return LaneResult(left, right, None, None, "车道不可用", confidence,
                          binary, edges, vertices)

    @staticmethod
    def _consensus(points, top, bottom, width):
        if len(points) < 2:
            return None, 0.
        segments = np.float32(points).reshape(-1, 2, 2)
        lengths = np.abs(segments[:, 1, 0] - segments[:, 0, 0])
        indices = np.argsort(lengths)[-24:]
        segments, lengths = segments[indices], lengths[indices]
        slopes = (segments[:, 1, 1] - segments[:, 0, 1]) / (
            segments[:, 1, 0] - segments[:, 0, 0])
        anchors = segments[:, 0]
        prediction = anchors[:, 1, None, None] + slopes[:, None, None] * (
            segments[None, :, :, 0] - anchors[:, 0, None, None])
        inliers = np.abs(segments[None, :, :, 1] - prediction).max(axis=2) <= max(4, .018 * width)
        winner = int(np.argmax(inliers @ lengths))
        support = segments[inliers[winner]].reshape(-1, 2)
        coverage = float(np.ptp(support[:, 0])) / (bottom - top)
        if coverage < .24:
            return None, 0.
        vy, vx, cy, cx = cv2.fitLine(support, cv2.DIST_HUBER, 0, .01, .01).ravel()
        if abs(vy) < 1e-3:
            return None, 0.
        slope = vx / vy
        line = (round(float(np.clip(cx + slope * (bottom - cy), 0, width - 1))), bottom,
                round(float(np.clip(cx + slope * (top - cy), 0, width - 1))), top)
        return line, min(1., coverage)

    @staticmethod
    def _valid_pair(left, right, width):
        lower = right[0] - left[0]
        upper = right[2] - left[2]
        return .16 * width <= lower <= .85 * width and .012 * width <= upper <= .82 * lower

    @staticmethod
    def _paint_supported(line, brightness, y_offset):
        """Require a bright stripe with darker pixels on both sides."""
        if line is None:
            return False
        x_bottom, y_bottom, x_top, y_top = line
        fractions = np.linspace(.08, .92, 24)
        y = np.rint(y_top + fractions * (y_bottom - y_top)).astype(np.intp) - y_offset
        x = np.rint(x_top + fractions * (x_bottom - x_top)).astype(np.intp)
        scale = brightness.shape[1] / 480
        center = max(1, round(3 * scale))
        flank = np.maximum(center + 2, np.rint((6 + fractions * 6) * scale)).astype(np.intp)
        valid = (x >= flank) & (x + flank < brightness.shape[1])
        if np.count_nonzero(valid) < 4:
            return False
        x, y, flank = x[valid], y[valid], flank[valid]
        middle = brightness[y[:, None], x[:, None] + np.arange(-center, center + 1)].max(axis=1)
        background = np.maximum(brightness[y, x - flank], brightness[y, x + flank])
        return np.count_nonzero(middle.astype(np.int16) - background >= 13) >= 4

    @staticmethod
    def _trim_to_road(left, right, width):
        lower = right[0] - left[0]
        upper = right[2] - left[2]
        if not .16 * width <= lower <= .85 * width or upper > .82 * lower:
            return None, None
        # The search region can extend above the horizon. Stop the overlay
        # below the intersection, where the two lines delimit visible road.
        fraction = max(0., (.025 * width - upper) / (lower - upper))
        if fraction > .66:
            return None, None
        y = round(left[3] + fraction * (left[1] - left[3]))
        left_x = round(left[2] + fraction * (left[0] - left[2]))
        right_x = round(right[2] + fraction * (right[0] - right[2]))
        if not .19 * width <= (left_x + right_x) / 2 <= .81 * width:
            return None, None
        return (left[0], left[1], left_x, y), (right[0], right[1], right_x, y)

    def _stabilize(self, index, line, width):
        last = self.side_lines[index]
        if line is None or last is None or max(abs(last[0] - line[0]), abs(last[2] - line[2])) > .075 * width:
            self.side_lines[index] = line
            self.side_hits[index] = int(line is not None)
            return None
        smoothed = tuple(round(.64 * a + .36 * b) for a, b in zip(last, line))
        self.side_lines[index] = smoothed
        self.side_hits[index] += 1
        return smoothed if self.side_hits[index] >= self.consecutive else None

    def _near_paint_pair(self, brightness, offset, width, bottom):
        """Find converging stripes with local contrast in the near road region."""
        top = int(bottom*.72)
        sy = np.arange(top+8,bottom-2,2)
        edges = cv2.Canny(brightness[top-offset:],18,52)
        candidates = cv2.HoughLinesP(edges,1,np.pi/180,9,
                                    minLineLength=max(7,width//55),maxLineGap=14)
        if candidates is None:
            return None
        halves = ([], [])
        for x1,y1,x2,y2 in candidates[:,0]:
            if abs(y2-y1)<6:
                continue
            slope = (x2-x1)/(y2-y1)
            if not .14<abs(slope)<2.9:
                continue
            near = x1+slope*(bottom-top-y1)
            far = x1-slope*y1
            if not width*.20<far<width*.84:
                continue
            side = int(slope>0)
            if not (.04*width <= near <= .52*width if not side else
                    .48*width <= near <= .96*width):
                continue
            xs = np.rint(far+slope*(sy-top)).astype(np.intp)
            ys = sy-offset
            flank = np.clip(np.rint(4+(sy-top)*.09),5,11).astype(np.intp)
            if np.any(xs-flank<0) or np.any(xs+flank>=width):
                continue
            middle = np.maximum.reduce([brightness[ys,xs+d] for d in (-2,-1,0,1,2)])
            background = np.maximum(brightness[ys,xs-flank],brightness[ys,xs+flank])
            contrast = np.maximum(middle.astype(np.int16)-background-14,0).clip(0,65)
            hits = np.count_nonzero(contrast)
            if hits<4:
                continue
            score = float(np.sum(contrast)/65)
            halves[side].append((score,near,far))
        pairs = []
        for l in sorted(halves[0],reverse=True)[:18]:
            for r in sorted(halves[1],reverse=True)[:18]:
                span = r[1]-l[1]
                far_gap = r[2]-l[2]
                if not .14*width<=span<=.55*width or not -.08*width<=far_gap<=.45*span:
                    continue
                midpoint = (r[1]+l[1])*.5
                score = l[0]+r[0]-15*abs(midpoint/width-self.camera_center_ratio)-10*abs(span/width-.28)
                pairs.append((score,l,r))
        if not pairs:
            return None
        score,l,r = max(pairs)
        start = min(bottom-14,top+max(0,round((.025*width-(r[2]-l[2]))*(bottom-top)/
                                             ((r[1]-l[1])-(r[2]-l[2])))))
        def line(item):
            return (round(item[1]),bottom,round(item[2]+(item[1]-item[2])*(start-top)/(bottom-top)),start)
        return line(l), line(r), min(1.,max(0.,score/21))

    def analyze(self, frame):
        h, w = frame.shape[:2]
        y_top, y_bottom = int(h*self.roi_top_pct/100), h-1
        # Keep a halo above the road polygon for the local filters and gradients.
        y_offset = max(0, y_top - 12) if self.crop_to_roi else 0
        hsv = cv2.cvtColor(frame[y_offset:], cv2.COLOR_BGR2HSV)
        white = cv2.inRange(hsv, (0, 0, self.white_min), (179, 85, 255))
        yellow = cv2.inRange(hsv, (12, 65, 90), (42, 255, 255))
        markings = cv2.bitwise_or(white, yellow)
        if self.local_contrast:
            brightness = hsv[:, :, 2]
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 7))
            narrow_bright = cv2.morphologyEx(brightness, cv2.MORPH_TOPHAT, kernel)
            neutral = cv2.inRange(hsv, (0, 0, 85), (179, 95, 255))
            markings |= cv2.bitwise_and(cv2.inRange(narrow_bright, 20, 255), neutral)
        markings = cv2.GaussianBlur(markings, (5, 5), 0)
        edges = cv2.Canny(markings, self.canny_low, self.canny_high)
        roi = np.zeros_like(edges)
        top_half = self.roi_top_half_pct/100
        bottom_half = self.roi_bottom_half_pct/100
        center = self.roi_center_ratio
        vertices = np.array([[(int((center-bottom_half)*w), y_bottom), (int((center-top_half)*w), y_top),
                              (int((center+top_half)*w), y_top), (int((center+bottom_half)*w), y_bottom)]], np.int32)
        cv2.fillPoly(roi, vertices - np.int32([0, y_offset]), 255)
        binary_roi = cv2.bitwise_and(markings, roi)
        edges_roi = cv2.bitwise_and(edges, roi)
        lines = cv2.HoughLinesP(edges_roi, 1, np.pi/180, self.hough_votes,
                                minLineLength=max(20, int(self.min_line_pct*w/100)), maxLineGap=35)
        left_points, right_points = [], []
        if lines is not None:
            for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
                y1 += y_offset
                y2 += y_offset
                if abs(y2-y1) < 15:
                    continue
                slope = (x2-x1)/(y2-y1)
                if not .15 <= abs(slope) <= 2.0:
                    continue
                x_at_bottom = x1 + slope*(y_bottom-y1)
                if slope < 0 and (center-.45)*w <= x_at_bottom <= (center+.03)*w:
                    left_points.extend(((y1,x1),(y2,x2)))
                elif slope > 0 and (center-.03)*w <= x_at_bottom <= (center+.45)*w:
                    right_points.extend(((y1,x1),(y2,x2)))

        def fit(points):
            if len(points) < 4:
                return None
            ys, xs = np.asarray(points, dtype=np.float32).T
            slope, intercept = np.polyfit(ys, xs, 1)
            return (int(np.clip(slope*y_bottom+intercept, 0, w-1)), y_bottom,
                    int(np.clip(slope*y_top+intercept, 0, w-1)), y_top)

        if y_offset:
            binary_roi = cv2.copyMakeBorder(binary_roi, y_offset, 0, 0, 0, cv2.BORDER_CONSTANT)
            edges_roi = cv2.copyMakeBorder(edges_roi, y_offset, 0, 0, 0, cv2.BORDER_CONSTANT)
        if self.stable_fit:
            left, left_support = self._consensus(left_points, y_top, y_bottom, w)
            right, right_support = self._consensus(right_points, y_top, y_bottom, w)
            if not self._paint_supported(left, hsv[:, :, 2], y_offset):
                left = None
            if not self._paint_supported(right, hsv[:, :, 2], y_offset):
                right = None
            if left and right:
                left, right = self._trim_to_road(left, right, w)
            elif left and left_support < .45:
                left = None
            elif right and right_support < .45:
                right = None
            if not (left and right) and self.roi_top_pct<69:
                near_pair = self._near_paint_pair(hsv[:,:,2],y_offset,w,y_bottom)
                if near_pair:
                    left,right,left_support = near_pair
                    right_support = left_support
            left, right = self._stabilize(0, left, w), self._stabilize(1, right, w)
            confidence = min(left_support, right_support) if left and right else (
                .5 * (left_support if left else right_support) if left or right else 0.)
            if left and right and not self._valid_pair(left, right, w):
                left = right = None
                confidence = 0.
        else:
            left, right = fit(left_points), fit(right_points)
            confidence = min(1., (len(left_points)+len(right_points))/24.) if left and right else 0.
        if not (left and right):
            return self._missing_result(left, right, binary_roi, edges_roi, vertices, confidence)
        lane_width = right[0]-left[0]
        if not self.stable_fit and not .25*w <= lane_width <= .85*w:
            return self._missing_result(left, right, binary_roi, edges_roi, vertices)
        center = (left[0]+right[0])/2
        offset = (self.camera_center_ratio*w-center)/lane_width
        offset = offset if self.previous is None else .65*self.previous+.35*offset
        self.previous = offset
        self.left_count = self.left_count+1 if offset < -self.departure_threshold else 0
        self.right_count = self.right_count+1 if offset > self.departure_threshold else 0
        departure = ("偏左" if self.left_count >= self.consecutive else
                     "偏右" if self.right_count >= self.consecutive else None)
        assist = "建议轻微向右修正" if offset < -.08 else "建议轻微向左修正" if offset > .08 else "保持车道中央"
        result = LaneResult(left, right, offset, departure, assist, confidence,
                            binary_roi, edges_roi, vertices)
        self.last_valid = result
        self.missing = 0
        return result


def cockpit_lane_analyzer():
    lane = LaneAnalyzer(consecutive=2)
    lane.roi_top_pct = 61
    lane.stable_fit = lane.crop_to_roi = lane.local_contrast = True
    return lane
