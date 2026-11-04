"""Render an H.264 clip with calibrated lane guides."""

import argparse
from fractions import Fraction
import json
from pathlib import Path

import cv2
import numpy as np


def sample_ridges(gray, anchor_y, guide):
    """Snap each guide to nearby narrow, bright paint, with a small correction budget."""
    h, w = gray.shape
    scale = w / 852
    margin = max(2, round(8 * scale))
    ys, errors = [], []
    for y in range(round(anchor_y[0]), min(h, round(anchor_y[1]) + 1), 2):
        fraction = (y - anchor_y[0]) / (anchor_y[1] - anchor_y[0])
        x = guide[0] + fraction * (guide[1] - guide[0])
        radius = round((15 + 9 * fraction) * scale)
        lo, hi = max(0, round(x) - radius - margin), min(w, round(x) + radius + margin)
        row = gray[y, lo:hi]
        if len(row) < 4 * margin:
            continue
        threshold = max(148, float(np.median(row)) + 29)
        edges = np.flatnonzero(np.diff(np.r_[False, row >= threshold, False]))
        candidates = []
        for start, stop in zip(edges[::2], edges[1::2]):
            center = lo + (start + stop - 1) / 2
            if (abs(center - x) > radius or not 2 <= stop - start <= max(5, round(26 * scale))
                    or start < margin or stop + margin > len(row)):
                continue
            flank = max(float(np.median(row[start-margin:start])),
                        float(np.median(row[stop:stop+margin])))
            if float(np.median(row[start:stop])) - flank >= 23:
                candidates.append(center)
        if candidates:
            ys.append(fraction)
            errors.append(min(candidates, key=lambda center: abs(center - x)) - x)
    if len(errors) < 7:
        return np.zeros(2)
    # A weak prior keeps the hidden end of a dashed marking from swinging
    # when only a short portion of the stripe is visible.
    design = np.column_stack((1 - np.array(ys), ys))
    weights = np.ones(len(errors))
    errors = np.asarray(errors)
    for _ in range(3):
        fit = np.linalg.solve(design.T @ (weights[:, None] * design) + 2.5 * np.eye(2),
                              design.T @ (weights * errors))
        weights = np.minimum(1, 4 * scale / np.maximum(.1, np.abs(design @ fit - errors)))
    return np.clip(fit, -16 * scale, 16 * scale)


def draw_guides(frame, anchor_y, draw_y, guides):
    scale = frame.shape[1] / 852
    for (x0, x1), limits in zip(guides, draw_y):
        t = (limits - anchor_y[0]) / (anchor_y[1] - anchor_y[0])
        points = [(round(x), round(y)) for x, y in zip(x0 + t * (x1 - x0), limits)]
        cv2.line(frame, *points, (33, 55, 39), max(3, round(8 * scale)), cv2.LINE_AA)
        cv2.line(frame, *points, (123, 255, 108), max(2, round(4 * scale)), cv2.LINE_AA)


def render(source, output, config):
    import av

    keys = np.asarray(config["keyframes"], dtype=np.float64)
    if (keys.ndim != 2 or keys.shape[1] not in (3, 5) or len(keys) < 2 or not np.isfinite(keys).all()
            or keys[0, 0] < 0 or not np.all(np.diff(keys[:, 0]) > 0)):
        raise ValueError("Guide keyframes need increasing timestamps and two x coordinates per line.")
    lanes = (keys.shape[1] - 1) // 2
    draw_ranges = np.asarray(config["draw_y"])
    if draw_ranges.shape == (2,):
        draw_ranges = np.tile(draw_ranges, (lanes, 1))
    if draw_ranges.shape != (lanes, 2):
        raise ValueError("draw_y must give a shared range or one range per line.")
    if source.resolve() == output.resolve():
        raise ValueError("Use a separate output file.")
    cap = cv2.VideoCapture(str(source))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not cap.isOpened() or not fps > 0:
        cap.release()
        raise ValueError(f"Cannot open {source}")
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    reference_w, reference_h = config["frame_size"]
    anchor_y = np.asarray(config["anchor_y"]) * h / reference_h
    draw_y = draw_ranges * h / reference_h
    start, stop = (round(t * fps) for t in keys[[0, -1], 0])
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    positions = []
    try:
        for i in range(start, stop):
            ok, frame = cap.read()
            if not ok:
                raise ValueError("Guide timestamps run past the end of the source video.")
            guides = (np.array([np.interp(i / fps, keys[:, 0], x) for x in keys[:, 1:].T])
                      .reshape(lanes, 2) * w / reference_w)
            if config.get("snap", True):
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                guides += np.array([sample_ridges(gray, anchor_y, g) for g in guides])
            positions.append(guides.ravel())

        # An offline symmetric smoother removes jitter without delaying turns.
        kernel = cv2.getGaussianKernel(9, 1.65).ravel()
        padded = np.pad(positions, ((4, 4), (0, 0)), mode="edge")
        smooth = np.column_stack([np.convolve(x, kernel, mode="valid") for x in padded.T])
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        with av.open(str(output), "w", options={"movflags": "+faststart"}) as mux:
            stream = mux.add_stream("libx264", rate=Fraction(fps).limit_denominator(1001))
            stream.width, stream.height, stream.pix_fmt = w, h, "yuv420p"
            stream.options = {"crf": "17", "preset": "medium"}
            for endpoints in smooth:
                ok, frame = cap.read()
                if not ok:
                    raise ValueError("Cannot reread the source video.")
                draw_guides(frame, anchor_y, draw_y, endpoints.reshape(lanes, 2))
                for packet in stream.encode(av.VideoFrame.from_ndarray(frame, format="bgr24")):
                    mux.mux(packet)
            for packet in stream.encode():
                mux.mux(packet)
    finally:
        cap.release()
    return len(positions), fps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--guides", type=Path, default=Path(__file__).with_name("lane_clip_guides.json"))
    args = parser.parse_args()
    cv2.setNumThreads(1)
    count, fps = render(args.source, args.output, json.loads(args.guides.read_text(encoding="utf-8")))
    print(f"{count} frames at {fps:.2f} fps: {args.output}")


if __name__ == "__main__":
    main()
