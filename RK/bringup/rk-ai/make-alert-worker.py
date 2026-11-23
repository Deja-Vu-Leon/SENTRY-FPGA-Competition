from pathlib import Path

root=Path(__file__).resolve().parent
s=(root/"four_camera.py").read_text(encoding="utf-8-sig")
s=s.replace("import cv2","from alert_archive import AlertArchive\n\nimport cv2",1)
s=s.replace("def objects(detector, frame, ch, monitor, timestamp):",
            "def objects(detector, frame, ch, monitor, timestamp, archive=None):")
s=s.replace('                    label += " ALERT"', '''                    label += " ALERT"
                    if archive is not None:
                        try:
                            archive.save(PORTS[ch], frame, det, risk)
                        except (OSError, cv2.error) as exc:
                            print(f"Alert archive: {exc}", file=sys.stderr, flush=True)''')
s=s.replace("    detector = open_detector(VEHICLES)",
            '    archive = AlertArchive(Path(__file__).resolve().parent / "alerts") if not args.smoke else None\n'
            '    detector = open_detector(VEHICLES)')
s=s.replace("objects(detector,frame,ch,monitors[ch],captured)",
            "objects(detector,frame,ch,monitors[ch],captured,archive)")
(root/"four_camera_features.py").write_text(s,encoding="utf-8")
