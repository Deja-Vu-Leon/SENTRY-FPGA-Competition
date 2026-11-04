"""Optional image enhancement for adverse-weather research; not a visibility guarantee."""
import cv2
import numpy as np


MODES = ("雾霾", "沙尘暴", "暴风雪")


def _clahe_bgr(frame, clip=2.0):
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def _gray_world(frame):
    mean = np.array(cv2.mean(frame)[:3])
    gains = np.clip(mean.mean() / np.maximum(mean, 1), .65, 1.65)
    return np.clip(frame.astype(np.float32) * gains, 0, 255).astype(np.uint8)


def _dehaze(frame):
    """Approximate dark-channel-prior recovery on a half-resolution transmission map."""
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (max(1, w//2), max(1, h//2)))
    blue, green, red = cv2.split(small)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    dark = cv2.erode(cv2.min(cv2.min(blue, green), red), kernel)
    top = max(1, dark.size//1000)
    idx = np.argpartition(dark.reshape(-1), -top)[-top:]
    bright = small.reshape(-1, 3)[idx]
    atmosphere = bright[np.argmax(bright.sum(axis=1))].astype(np.float32)
    atmosphere = np.maximum(atmosphere, 80)
    blue, green, red = [cv2.multiply(channel, 1.0 / float(level), dtype=cv2.CV_32F)
                        for channel, level in zip((blue, green, red), atmosphere)]
    minimum = cv2.erode(cv2.min(cv2.min(blue, green), red), kernel)
    transmission = np.clip(1.0 - .82 * minimum, .40, 1.0)
    transmission = cv2.GaussianBlur(transmission, (0, 0), 3)
    transmission = cv2.resize(transmission, (w, h)).astype(np.float32)
    recovered = []
    for channel, level in zip(cv2.split(frame), atmosphere):
        level = float(level)
        centered = cv2.subtract(channel, level, dtype=cv2.CV_32F)
        recovered.append(cv2.add(cv2.divide(centered, transmission), level))
    recovered = cv2.merge(recovered)
    return np.clip(recovered, 0, 255).astype(np.uint8)


def enhance(frame, mode="雾霾", strength=50):
    """Return a new uint8 BGR frame; strength=0 preserves the source exactly."""
    if mode not in MODES:
        raise ValueError(f"unsupported weather mode: {mode}")
    if not 0 <= strength <= 100:
        raise ValueError("strength must be 0..100")
    if strength == 0:
        return frame.copy()
    if mode == "雾霾":
        candidate = _clahe_bgr(_dehaze(frame), 1.1)
    elif mode == "沙尘暴":
        candidate = _clahe_bgr(_dehaze(_gray_world(frame)), 1.1)
    else:
        candidate = _clahe_bgr(frame, 2.6)
        candidate = np.clip(candidate.astype(np.float32)*1.08-10, 0, 255).astype(np.uint8)
    blended = cv2.addWeighted(frame, 1.0-strength/100, candidate, strength/100, 0)
    if mode == "暴风雪":
        return blended
    blue, green, red = cv2.split(frame)
    ceiling = cv2.max(cv2.max(cv2.max(blue, green), red), 225)
    blue, green, red = cv2.split(blended)
    excess = cv2.subtract(cv2.max(cv2.max(blue, green), red), ceiling)
    return cv2.merge([cv2.subtract(channel, excess) for channel in (blue, green, red)])
