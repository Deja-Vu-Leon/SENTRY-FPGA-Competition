"""Compact RGB image histogram for the live dashboard."""
import cv2
import numpy as np


def render_histogram(frame, width=300, height=72):
    chart = np.full((height, width, 3), (20, 32, 45), np.uint8)
    sample = cv2.resize(frame, (320, 180))
    for channel, color in ((0, (255, 105, 85)), (1, (75, 215, 105)), (2, (75, 105, 255))):
        hist = cv2.calcHist([sample], [channel], None, [256], [0, 256]).reshape(-1)
        hist = np.log1p(hist)
        peak = max(float(hist.max()), 1.0)
        ys = (height-10 - (hist/peak)*(height-22)).astype(np.int32)
        xs = np.linspace(8, width-9, 256).astype(np.int32)
        points = np.stack((xs, ys), axis=1)
        cv2.polylines(chart, [points], False, color, 1, cv2.LINE_AA)
    cv2.line(chart, (8, height-10), (width-9, height-10), (90, 110, 130), 1)
    return chart
