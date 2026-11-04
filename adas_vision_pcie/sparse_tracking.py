"""Refresh object detections periodically and fit boxes on intervening frames."""

import cv2
import numpy as np

from vision import Detection


class DetectionCadence:
    """Track within one detection interval, then re-anchor to the detector."""

    def __init__(self, interval):
        self.interval = interval
        self.reset()

    def reset(self):
        self.key_gray = None
        self.key_time = None
        self.remaining = 0
        self.detections = []
        self.features = []

    def update(self, detector, original, enhanced, now, *, select_boxes=None):
        if self.interval == 1:
            boxes = detector.detect(enhanced)
            return select_boxes(boxes) if select_boxes is not None else boxes, detector.inference_ms

        gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (max(1, gray.shape[1] // 2), max(1, gray.shape[0] // 2)),
                          interpolation=cv2.INTER_AREA)
        h, w = original.shape[:2]
        sx, sy = gray.shape[1] / w, gray.shape[0] / h
        if (self.remaining and self.key_gray.shape == gray.shape and
                now - self.key_time <= .40 and
                cv2.mean(cv2.absdiff(self.key_gray, gray))[0] < 20):
            tracked = self._track(gray, sx, sy, w, h)
            if tracked is not None:
                self.remaining -= 1
                return tracked, None

        boxes = detector.detect(enhanced)
        if select_boxes is not None:
            boxes = select_boxes(boxes)
        self.key_gray = gray
        self.key_time = now
        self.remaining = self.interval - 1
        self.detections = boxes
        self.features = []
        for det in boxes:
            x1, y1, x2, y2 = det.box
            left, top = round(x1 * sx), round(y1 * sy)
            right, bottom = round(x2 * sx), round(y2 * sy)
            roi = gray[top:bottom, left:right]
            if min(roi.shape) < 5:
                continue
            corners = cv2.goodFeaturesToTrack(roi, maxCorners=14, qualityLevel=.015,
                                              minDistance=3, blockSize=3)
            if corners is not None and len(corners) >= 3:
                corners[:, 0] += (left, top)
                self.features.append((det, corners))
        return boxes, detector.inference_ms

    def _track(self, gray, sx, sy, width, height):
        if not self.detections:
            return []
        if not self.features:
            return None
        old = np.concatenate([points for _, points in self.features])
        params = dict(winSize=(15, 15), maxLevel=2,
                      criteria=(cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 15, .03))
        new, forward, _ = cv2.calcOpticalFlowPyrLK(self.key_gray, gray, old, None, **params)
        if new is None:
            return None
        valid = forward.ravel().astype(bool) & np.isfinite(new).all(axis=(1, 2))
        new[~valid] = old[~valid]
        returned, backward, _ = cv2.calcOpticalFlowPyrLK(gray, self.key_gray, new, None, **params)
        if returned is None:
            return None
        valid &= backward.ravel().astype(bool)
        valid &= np.max(np.abs(returned - old), axis=(1, 2)) <= 1.0
        detections = []
        offset = 0
        for det, points in self.features:
            span = slice(offset, offset + len(points))
            offset += len(points)
            good = valid[span]
            if np.count_nonzero(good) < 3:
                continue
            transform, inliers = cv2.estimateAffinePartial2D(
                old[span][good], new[span][good], method=cv2.RANSAC,
                ransacReprojThreshold=1.2, maxIters=30, refineIters=3)
            if transform is None or np.count_nonzero(inliers) < 3:
                continue
            scale = np.hypot(transform[0, 0], transform[1, 0])
            if not .80 <= scale <= 1.25 or abs(transform[0, 1]) > .20:
                continue
            x1, y1, x2, y2 = det.box
            center = np.float32([((x1 + x2) * sx / 2, (y1 + y2) * sy / 2)])
            moved = cv2.transform(center[None, :, :], transform)[0, 0]
            cx, cy = moved[0] / sx, moved[1] / sy
            box_w, box_h = (x2 - x1) * scale / 2, (y2 - y1) * scale / 2
            left = round(np.clip(cx - box_w, 0, width - 1))
            top = round(np.clip(cy - box_h, 0, height - 1))
            right = round(np.clip(cx + box_w, 0, width - 1))
            bottom = round(np.clip(cy + box_h, 0, height - 1))
            if right > left and bottom > top:
                detections.append(Detection((left, top, right, bottom), det.score, det.label))
        return detections or None
