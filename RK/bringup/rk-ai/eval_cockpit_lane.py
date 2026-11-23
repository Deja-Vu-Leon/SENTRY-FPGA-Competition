"""Evaluate the two ego-lane boundaries against independently marked points."""
import argparse
import json
from pathlib import Path

import cv2
from cockpit_lane import cockpit_lane_analyzer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path, help="JSON lines with raw_file, h_samples, lanes and optional context frames")
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    total = correct = frames = 0
    model = cockpit_lane_analyzer()
    for row in args.labels.read_text(encoding="utf-8").splitlines():
        if not row.strip():
            continue
        entry = json.loads(row)
        image = cv2.imread(str(args.images / entry["raw_file"]))
        if image is None:
            raise ValueError(f"missing input image: {entry['raw_file']}")
        height, width = image.shape[:2]
        ys = entry["h_samples"]
        if any(len(lane) != len(ys) for lane in entry["lanes"]):
            raise ValueError(f"inconsistent lane annotations: {entry['raw_file']}")
        visible = [(lane, next((x for x in reversed(lane) if x>=0), -1))
                   for lane in entry["lanes"]]
        left = max((p for p in visible if 0<=p[1]<width/2), key=lambda p:p[1], default=None)
        right = min((p for p in visible if p[1]>=width/2), key=lambda p:p[1], default=None)
        if left is None or right is None:
            continue
        model.reset()
        for path in entry.get("context", []):
            previous = cv2.imread(str(args.images/path))
            if previous is None:
                raise ValueError(f"missing context frame: {path}")
            model.analyze(cv2.resize(previous,(420,236),interpolation=cv2.INTER_AREA))
        prediction = model.analyze(cv2.resize(image, (420, 236), interpolation=cv2.INTER_AREA))
        frames += 1
        for truth, line in ((left[0], prediction.left), (right[0], prediction.right)):
            for y, target in zip(ys, truth):
                if target<0 or y < height*.55:
                    continue
                total += 1
                if line:
                    x1, y1, x2, y2 = line
                    scaled_y = y*236/height
                    if min(y1,y2)<=scaled_y<=max(y1,y2) and y1!=y2:
                        estimated = (x1+(x2-x1)*(scaled_y-y1)/(y2-y1))*width/420
                        correct += abs(estimated-target)<=20*width/1280
    if not total:
        raise ValueError("no annotated ego-lane points in the evaluated region")
    accuracy = 100*correct/total
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(f"{accuracy:.3f} {frames}\n", encoding="ascii")
    tmp.replace(args.output)
    print(f"{accuracy:.2f}% ({correct}/{total} points, {frames} images)")
    return 0 if accuracy>=88 else 1


if __name__ == "__main__":
    raise SystemExit(main())
