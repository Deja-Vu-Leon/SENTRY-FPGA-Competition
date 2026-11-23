"""Compare playback lane tracking against the recorded demo guide geometry."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from cockpit_lane import cockpit_lane_analyzer
from video_lane import VideoLaneAnalyzer


def score(line, ys, xs):
    if line is None:
        return 0
    x0,y0,x1,y1 = line
    if y0==y1:
        return 0
    estimate = x0+(x1-x0)*(ys-y0)/(y1-y0)
    return int(np.count_nonzero((np.abs(estimate-xs)<=420*20/1280) &
                                (ys>=min(y0,y1)-3) & (ys<=max(y0,y1)+3)))


def evaluate(path, config):
    old, new = cockpit_lane_analyzer(),VideoLaneAnalyzer()
    capture = cv2.VideoCapture(str(path))
    rate = capture.get(cv2.CAP_PROP_FPS)
    if rate<=0:
        raise OSError(f"Could not open {path}")
    keys = np.asarray(config["keyframes"])
    fh,fw = config["frame_size"][1],config["frame_size"][0]
    bounds = np.asarray(config["draw_y"],dtype=float).reshape(-1,2)
    sides = [0,1] if keys.shape[1]==5 else [1]
    old_hits = new_hits = count = frames = guide_frames = 0
    fps_sample = round(rate/6.7)
    for i in range(int(capture.get(cv2.CAP_PROP_FRAME_COUNT))):
        if not capture.grab():
            break
        if i%fps_sample:
            continue
        ok, frame = capture.retrieve()
        if not ok:
            break
        frame = cv2.resize(frame,(420,236),interpolation=cv2.INTER_AREA)
        t = i/rate
        previous, result = old.analyze(frame),new.analyze(frame,t)
        if i<fps_sample:
            continue
        frames+=1
        guide_frames += result.source=="guide"
        old_lines,new_lines = ((previous.left,previous.right),(result.left,result.right))
        for j, side in enumerate(sides):
            selected = bounds[min(j,len(bounds)-1)]
            anchor = np.asarray(config["anchor_y"])
            ys = np.linspace(selected[0]+.18*np.ptp(selected),selected[1]-.18*np.ptp(selected),5)
            ends = np.array([np.interp(t+keys[0,0],keys[:,0],keys[:,1+j*2+k]) for k in (0,1)])
            xs = (ends[0]+(ends[1]-ends[0])*(ys-anchor[0])/np.ptp(anchor))*420/fw
            ys *= 236/fh
            old_hits += score(old_lines[side],ys,xs)
            new_hits += score(new_lines[side],ys,xs)
            count += len(xs)
    capture.release()
    return dict(frames=frames,guide_frames=guide_frames,points=count,baseline=old_hits,matched=new_hits)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media",type=Path)
    parser.add_argument("guides",type=Path)
    parser.add_argument("output",type=Path)
    args = parser.parse_args()
    configs = ["lane_clip_guides.json","lane_clips/city.json","lane_clips/tunnel.json","lane_clips/fog.json"]
    results = {}
    for index,name in enumerate(configs,1):
        video = next(args.media.glob(f"{index:02}-*.mp4"))
        results[video.name] = evaluate(video,json.loads((args.guides/name).read_text(encoding="utf8")))
    results["total"] = {key:sum(item[key] for item in results.values()) for key in next(iter(results.values()))}
    args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps(results,ensure_ascii=True,indent=2))


if __name__ == "__main__":
    main()
