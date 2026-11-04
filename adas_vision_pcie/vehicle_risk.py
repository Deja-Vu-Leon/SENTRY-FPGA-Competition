"""Lightweight temporal risk estimates from existing RKNN vehicle boxes."""

from collections import deque
from dataclasses import dataclass, field
from statistics import median

from tracker import WIDTH_M


RESULT_MAX_AGE = 1.2
TRACK_MAX_AGE = .60
UNKNOWN, NORMAL, CAUTION, HIGH = "unknown", "normal", "caution", "high"
CRITICAL_TTC, CAUTION_TTC = 2.2, 4.0


def iou(first, second):
    x1, y1, x2, y2 = first
    a1, b1, a2, b2 = second
    common = max(0, min(x2, a2) - max(x1, a1)) * max(0, min(y2, b2) - max(y1, b1))
    if not common:
        return 0.
    return common / ((x2-x1)*(y2-y1) + (a2-a1)*(b2-b1) - common)


def filter_vehicle_duplicates(detections):
    """Keep the stronger box when the same vehicle has overlapping class labels."""
    kept = []
    for det in sorted(detections, key=lambda d: d.score, reverse=True):
        if det.label in WIDTH_M and any(
                other.label in WIDTH_M and iou(det.box, other.box) >= .72 for other in kept):
            continue
        kept.append(det)
    return kept


@dataclass(frozen=True)
class VehicleRisk:
    location: float
    distance_m: float | None = None
    level: str = UNKNOWN
    reason: str = ""
    ttc_s: float | None = None
    closing_kmh: float | None = None
    speed_kmh: float | None = None


@dataclass
class _Track:
    box: tuple
    label: str
    seen: float
    samples: deque = field(default_factory=lambda: deque(maxlen=9))
    reason: str = ""
    clear_hits: int = 0
    closing_mps: float | None = None


def box_distance(box, width, focal_ratio):
    left, _, right, _ = box
    if right-left < 12 or left <= 2 or right >= width-3:
        return None
    return focal_ratio * width / (right-left)


def closing_speed(samples):
    """Signed change in range from spaced NPU boxes. Positive means closing."""
    if len(samples) < 4 or samples[-1][0] - samples[0][0] < .45:
        return None
    rates = [(old_d-new_d)/(new_t-old_t)
             for i, (old_t, old_d) in enumerate(samples)
             for new_t, new_d in samples[i+1:] if new_t-old_t >= .15]
    rate = median(rates)
    reference = median(d for _, d in samples)
    shift = median(d for _, d in samples[:2]) - median(d for _, d in samples[-2:])
    distances = [d + rate * (t - samples[-1][0]) for t, d in samples]
    expected = median(distances)
    residual = median(abs(d - expected) for d in distances)
    if abs(rate) > 65 or residual > max(.55, .055 * reference):
        return None
    if abs(rate) < .75:
        return 0. if abs(shift) <= max(.55, .035 * reference) else None
    if shift * rate <= 0 or abs(shift) < max(.45, .035 * reference, 2.2 * residual):
        return None
    return rate


class VehicleMonitor:
    def __init__(self, focal_ratio, near_m, *, rear_view=False):
        self.focal_ratio = focal_ratio
        self.near_m = near_m
        self.rear_view = rear_view
        self.tracks = []
        self.last_time = None

    def reset(self):
        self.tracks.clear()
        self.last_time = None

    def update(self, detections, width, now, *, measured, ego_kmh=None):
        """Return risk keyed by the current detection index, never by a stale box."""
        if self.last_time is not None and now < self.last_time:
            self.reset()
        self.last_time = now
        self.tracks = [track for track in self.tracks if now-track.seen <= TRACK_MAX_AGE]
        vehicles = [(i, det) for i, det in enumerate(detections) if det.label in WIDTH_M]
        matches = {}
        used = set()
        pairs = [(iou(det.box, tr.box), i, j)
                 for i, det in vehicles for j, tr in enumerate(self.tracks) if det.label == tr.label]
        for overlap, i, j in sorted(pairs, reverse=True):
            if overlap >= .23 and i not in matches and j not in used:
                matches[i] = self.tracks[j]
                used.add(j)
        if measured:
            # An NPU frame that misses a vehicle breaks the measurement sequence.
            self.tracks = [track for j, track in enumerate(self.tracks) if j in used]
        risks = {}
        for i, det in vehicles:
            location = (det.box[0]+det.box[2]) / (2*width)
            track = matches.get(i)
            if track is None and measured:
                track = _Track(det.box, det.label, now)
                self.tracks.append(track)
            ratio = box_distance(det.box, width, self.focal_ratio)
            distance_sample = ratio * WIDTH_M[det.label] if ratio is not None else None
            if measured:
                track.seen = now
                track.box = det.box
            if track is None or distance_sample is None or not 1 <= distance_sample <= 150:
                if measured and track is not None:
                    track.samples.clear()
                    track.reason, track.clear_hits = "", 0
                    track.closing_mps = None
                risks[i] = VehicleRisk(location)
                continue
            track.box = det.box
            fresh_sample = measured and (not track.samples or now > track.samples[-1][0])
            if fresh_sample:
                track.samples.append((now, distance_sample))
                while now-track.samples[0][0] > 1.2:
                    track.samples.popleft()
            samples = list(track.samples)
            if not samples:
                risks[i] = VehicleRisk(location)
                continue
            distance = median(d for _, d in samples[-3:])
            if fresh_sample:
                rate = closing_speed(samples)
                previous = track.closing_mps
                track.closing_mps = (.45*previous + .55*rate if previous is not None and
                                     rate is not None and previous*rate > 0 else rate)
            rate = track.closing_mps
            ttc = distance / rate if rate is not None and rate >= 1.2 else None
            in_path = .34 <= location <= .66
            if fresh_sample:
                close = len(samples) >= 2 and all(d <= self.near_m for _, d in samples[-2:])
                closing = in_path and distance <= 65 and ttc is not None and ttc <= CRITICAL_TTC
                if close or closing:
                    track.reason = "距离过近" if close else "快速接近"
                    track.clear_hits = 0
                elif track.reason:
                    if distance > self.near_m * 1.2 and (ttc is None or ttc > 2.8 or not in_path):
                        track.clear_hits += 1
                        if track.clear_hits >= 3:
                            track.reason = ""
                    else:
                        track.clear_hits = 0
            pending = len(samples) < 2 or distance <= self.near_m
            reason = track.reason
            if reason:
                level = HIGH
            elif pending:
                level = UNKNOWN
            elif in_path and distance <= 65 and ttc is not None and ttc <= CAUTION_TTC:
                level, reason = CAUTION, "接近中"
            elif (in_path and not self.rear_view and ego_kmh is not None and ego_kmh >= 15 and
                  distance / (ego_kmh / 3.6) <= 1.2 and (rate is None or rate >= -1.)):
                level, reason = CAUTION, "跟车时距短"
            else:
                level = NORMAL
            relative = rate * 3.6 if rate is not None else None
            speed = None
            if ego_kmh is not None and relative is not None and in_path:
                candidate = ego_kmh + relative if self.rear_view else ego_kmh - relative
                if 0 <= candidate <= 200:
                    speed = candidate
            risks[i] = VehicleRisk(location, distance, level, reason, ttc, relative, speed)
        return risks
