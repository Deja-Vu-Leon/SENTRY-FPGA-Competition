from pathlib import Path
from tempfile import TemporaryDirectory
import cv2
from alert_archive import AlertArchive
from four_camera_features import FIRST, VEHICLES, open_detector, objects, VehicleMonitor

with TemporaryDirectory(dir=".") as folder:
    archive=AlertArchive(folder)
    detector=open_detector(VEHICLES)
    source=cv2.VideoCapture(str(FIRST/"media/highway.mp4"))
    try:
        monitor=VehicleMonitor(.9,10.)
        for i in range(20):
            ok,frame=source.read()
            if not ok: break
            objects(detector,cv2.resize(frame,(420,236)),0,monitor,i*.12,archive)
    finally:
        source.release()
        detector.close()
    events=list(Path(folder).glob("*.json"))
    assert events and (Path(folder)/"index.tsv").stat().st_size
    assert all(cv2.imread(str(event.with_suffix(".jpg"))).shape[:2]==(236,420)
               and event.with_suffix(".xrgb").stat().st_size==420*236*4 for event in events)
    print("Recorded road alert: metadata, JPEG, raw review image and index verified.")
