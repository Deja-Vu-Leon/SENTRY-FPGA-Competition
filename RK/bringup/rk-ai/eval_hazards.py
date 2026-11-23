"""Evaluate released weights on local dataset images and their original labels."""
import argparse
import csv
import json
from pathlib import Path
import time

import cv2
import numpy as np

from hazard_model import (CRACK_MODEL, CRACK_THRESHOLDS, CRACKS, SLOPE_MODEL,
                          SLOPE_THRESHOLDS, SLOPE, HazardModel, box_iou)


def ground_truth(path,width,height):
    if not path.exists():
        return None
    boxes = []
    for row in path.read_text(encoding="utf8").splitlines():
        kind,*values = row.split()
        values = np.asarray(values,float)
        if len(values)==4:
            x,y,w,h = values
            box = ((x-w/2)*width,(y-h/2)*height,(x+w/2)*width,(y+h/2)*height)
        else:
            points = values.reshape(-1,2)*(width,height)
            box = (*points.min(axis=0),*points.max(axis=0))
        boxes.append((int(kind),tuple(map(round,box))))
    return boxes


def evaluate(directory, model, accepted, *, output=None, preview_size=None):
    if output is not None:
        previews = output/"predictions"
        previews.mkdir(parents=True,exist_ok=True)
    counts = dict(images=0,labeled_images=0,images_with_detection=0,tp=0,fp=0,fn=0)
    rows, times = [], []
    for path in sorted((directory/"images").iterdir()):
        image = cv2.imdecode(np.fromfile(path,dtype=np.uint8),cv2.IMREAD_COLOR)
        if image is None:
            continue
        if preview_size:
            image = cv2.resize(image,preview_size,interpolation=cv2.INTER_AREA)
        counts["images"] += 1
        start = time.perf_counter()
        found = [x for x in model.detect(image,return_masks=output is not None and not preview_size)
                 if x.kind in accepted]
        latency = (time.perf_counter()-start)*1000
        times.append(latency)
        counts["images_with_detection"] += bool(found)
        height,width = image.shape[:2]
        truth = ground_truth(directory/"labels"/(path.stem+".txt"),width,height)
        remaining = {i for i,(kind,_) in enumerate(truth or []) if kind in accepted}
        tp = 0
        if truth is not None:
            counts["labeled_images"] += 1
            for hit in found:
                matches = [(box_iou(hit.box,truth[i][1]),i) for i in remaining if truth[i][0]==hit.kind]
                if matches:
                    overlap,i = max(matches)
                    if overlap>=.5:
                        remaining.remove(i)
                        tp +=1
            counts["tp"] += tp
            counts["fp"] += len(found)-tp
            counts["fn"] += len(remaining)
        rows.append(dict(file=path.name,detections=len(found),matched=tp if truth is not None else "",
                         expected=sum(kind in accepted for kind,_ in truth) if truth is not None else "",
                         model_ms=round(latency,1),classes="; ".join(f"{model.classes[x.kind]} {x.score:.3f}" for x in found)))
        if output is None:
            continue
        for hit in found:
            color = (95,188,255)
            if hit.mask is not None:
                image[hit.mask] = (.64*image[hit.mask]+.36*np.array(color)).astype(np.uint8)
            x,y,r,b = hit.box
            cv2.rectangle(image,(x,y),(r,b),color,max(2,width//420))
            cv2.putText(image,f"{model.classes[hit.kind]} {hit.score:.2f}",(x,max(24,y-7)),
                        cv2.FONT_HERSHEY_SIMPLEX,max(.5,width/1200),color,2,cv2.LINE_AA)
        for kind,(x,y,r,b) in truth or []:
            if kind in accepted:
                cv2.rectangle(image,(x,y),(r,b),(180,235,116),1)
        if max(width,height)>1080:
            image = cv2.resize(image,(round(width*1080/max(width,height)),round(height*1080/max(width,height))))
        cv2.imencode(".jpg", image)[1].tofile(previews/(path.stem+".jpg"))
    if not rows:
        raise ValueError(f"No images found in {directory}")
    if output is not None:
        with (output/"results.csv").open("w",encoding="utf-8-sig",newline="") as stream:
            report = csv.DictWriter(stream,fieldnames=list(rows[0]))
            report.writeheader()
            report.writerows(rows)
    counts["median_model_ms"] = round(float(np.median(times)),1)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset",type=Path)
    parser.add_argument("models",type=Path)
    parser.add_argument("--channel",choices=("crack","slope"),required=True)
    parser.add_argument("--compare-preview",action="store_true",help="compare old and new RK inference input and weights")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    if args.channel=="crack":
        current,baseline = (*CRACK_MODEL,CRACK_THRESHOLDS),("rdd_yolo12n_320.onnx",320,.25)
        classes = CRACKS
        accepted = (0,1,2)
    else:
        current,baseline = (*SLOPE_MODEL,SLOPE_THRESHOLDS),("landslide_320.onnx",320,.35)
        classes = SLOPE
        accepted = (0,1)
    name,size,thresholds = current
    net = HazardModel(args.models/name,size,classes,thresholds,masks=args.channel=="slope")
    updated_size = (840,472) if args.compare_preview else None
    results = evaluate(args.dataset,net,accepted,output=args.dataset,preview_size=updated_size)
    if args.compare_preview:
        name,size,threshold = baseline
        base = HazardModel(args.models/name,size,classes,threshold)
        results = dict(baseline=evaluate(args.dataset,base,accepted,preview_size=(420,236)),updated=results)
    (args.dataset/"summary.json").write_text(json.dumps(results,indent=2),encoding="utf8")
    print(json.dumps(results),flush=True)


if __name__ == "__main__":
    main()
