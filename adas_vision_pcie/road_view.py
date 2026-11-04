"""Visual summaries of measured lanes and tracked vehicles.

The perspective panel is a schematic, not metric 3D reconstruction.
"""
import cv2
import numpy as np


def paint_lane_region(frame, lane):
    """Tint the estimated current lane and the adjacent right region."""
    if lane is None or lane.offset_fraction is None or not (lane.left and lane.right):
        return frame
    h, w = frame.shape[:2]
    left, right = lane.left, lane.right
    top_y = max(left[3], right[3])
    bottom_y = min(left[1], right[1])
    if bottom_y <= top_y or right[0] <= left[0] or right[2] <= left[2]:
        return frame
    overlay = frame.copy()
    current = np.array([[left[0], bottom_y], [left[2], top_y],
                        [right[2], top_y], [right[0], bottom_y]], np.int32)
    cv2.fillPoly(overlay, [current], (190, 110, 5))  # translucent teal in BGR
    width_top = right[2] - left[2]
    width_bottom = right[0] - left[0]
    adjacent = np.array([[right[0], bottom_y], [right[2], top_y],
                         [min(w-1, right[2]+width_top), top_y],
                         [min(w-1, right[0]+width_bottom), bottom_y]], np.int32)
    if adjacent[2, 0] > adjacent[1, 0] and adjacent[3, 0] > adjacent[0, 0]:
        cv2.fillPoly(overlay, [adjacent], (175, 55, 30))
    cv2.addWeighted(overlay, .35, frame, .65, 0, dst=frame)
    for line in (left, right):
        cv2.line(frame, (line[0], line[1]), (line[2], line[3]),
                 (50, 255, 65), 4, cv2.LINE_AA)
    return frame


def render_road_scene(width, height, lane, targets, source_width=960):
    """Draw a 2.5D road diagram from image positions and rough distances."""
    w, h = max(120, int(width)), max(160, int(height))
    image = np.full((h, w, 3), (25, 17, 11), np.uint8)
    horizon = int(h*.24)
    cv2.rectangle(image, (0, 0), (w, horizon), (48, 35, 23), -1)
    cx = w//2
    offset = 0 if lane is None or lane.offset_fraction is None else float(np.clip(lane.offset_fraction, -.4, .4))
    vanishing_x = int(cx - offset*w*.18)
    road_top = max(12, int(w*.09))
    road_bottom = int(w*.45)
    road = np.array([[vanishing_x-road_top, horizon], [vanishing_x+road_top, horizon],
                     [cx+road_bottom, h-1], [cx-road_bottom, h-1]], np.int32)
    cv2.fillPoly(image, [road], (61, 62, 65))
    cv2.polylines(image, [road], True, (115, 180, 190), 2, cv2.LINE_AA)
    lane_known = lane is not None and lane.offset_fraction is not None
    boundary_color = (55, 235, 75) if lane_known else (105, 115, 125)
    for side in (-1, 1):
        cv2.line(image, (vanishing_x+side*road_top//2, horizon),
                 (cx+side*road_bottom//2, h), boundary_color, 2, cv2.LINE_AA)
    for a, b in ((.09, .12), (.21, .26), (.38, .46), (.62, .73)):
        y1, y2 = int(horizon+(h-horizon)*a), int(horizon+(h-horizon)*b)
        x1 = int(vanishing_x+(cx-vanishing_x)*a)
        x2 = int(vanishing_x+(cx-vanishing_x)*b)
        cv2.line(image, (x1, y1), (x2, y2), (205, 215, 220), 2, cv2.LINE_AA)
    for depth in np.linspace(.08, .96, 18):
        y = int(horizon + depth**1.55*(h-horizon))
        spread = int(road_top + (road_bottom-road_top)*depth**1.55)
        for side in (-1, 1):
            cv2.circle(image, (int(vanishing_x+(cx-vanishing_x)*depth**1.55)+side*spread, y),
                       max(1, int(depth*2.5)), (90, 155, 205), -1, cv2.LINE_AA)
    risk_color = {"高": (65, 73, 245), "中": (66, 175, 255), "低": (120, 210, 66)}
    for target in sorted((t for t in targets if not t.stale),
                         key=lambda t: t.distance_m, reverse=True):
        depth = 1.0 - float(np.clip(target.distance_m/120.0, .03, .95))
        perspective = depth**1.5
        y = int(horizon + perspective*(h-horizon)*.72)
        camera_x = ((target.box[0]+target.box[2])/2/source_width-.5)*2
        x = int(vanishing_x+(cx-vanishing_x)*perspective + camera_x*w*(.12+.35*perspective))
        size = max(5, int(5+20*perspective))
        color = risk_color.get(target.risk, (170, 170, 170))
        body = np.array([[x-size, y], [x-size//2, y-size], [x+size//2, y-size],
                         [x+size, y], [x+size, y+size//2], [x-size, y+size//2]], np.int32)
        cv2.fillPoly(image, [body], color)
        cv2.polylines(image, [body], True, (245, 245, 245), 1, cv2.LINE_AA)
        cv2.line(image, (x-size, y), (x+size, y), (245, 245, 245), 1)
        cv2.putText(image, f"{target.id} {target.distance_m:.0f}m", (max(2, x-size), max(15, y-size-4)),
                    cv2.FONT_HERSHEY_SIMPLEX, .35, (235, 240, 245), 1, cv2.LINE_AA)
    ego_y = int(h*.87)
    ego = np.array([[cx-9, ego_y-18], [cx+9, ego_y-18], [cx+16, ego_y+9],
                    [cx+11, ego_y+16], [cx-11, ego_y+16], [cx-16, ego_y+9]], np.int32)
    cv2.fillPoly(image, [ego], (245, 210, 75))
    cv2.polylines(image, [ego], True, (250, 250, 250), 1, cv2.LINE_AA)
    cv2.line(image, (cx-10, ego_y), (cx+10, ego_y), (100, 75, 30), 2)
    cv2.putText(image, "3D ROAD / SCHEMATIC", (8, 20), cv2.FONT_HERSHEY_SIMPLEX,
                .42, (140, 225, 225), 1, cv2.LINE_AA)
    if not lane_known:
        cv2.putText(image, "LANE UNAVAILABLE", (8, h-12), cv2.FONT_HERSHEY_SIMPLEX,
                    .36, (170, 190, 210), 1, cv2.LINE_AA)
    return image
