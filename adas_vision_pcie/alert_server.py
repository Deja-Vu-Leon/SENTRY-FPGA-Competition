"""Store RK risk snapshots off the video thread and serve them over an SSH tunnel."""

from contextlib import closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from queue import Empty, Full, Queue
import sqlite3
from threading import Event, Thread
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import cv2

from vehicle_risk import HIGH


class AlertRelay:
    def __init__(self, port, database):
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS relay (id TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS alerts (seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "event TEXT NOT NULL, jpg BLOB NOT NULL)")
            row = db.execute("SELECT id FROM relay LIMIT 1").fetchone()
            self.source_id = row[0] if row else uuid4().hex
            if not row:
                db.execute("INSERT INTO relay VALUES (?)", (self.source_id,))
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                url = urlsplit(self.path)
                try:
                    if url.path == "/events":
                        query = parse_qs(url.query)
                        after = max(0, int(query.get("after", ["0"])[0]))
                        with closing(sqlite3.connect(relay.path)) as db:
                            rows = db.execute("SELECT seq, event FROM alerts WHERE seq > ? "
                                              "ORDER BY seq LIMIT 40", (after,)).fetchall()
                        payload = {"source_id": relay.source_id,
                                   "events": [dict(json.loads(event), seq=seq) for seq, event in rows]}
                        self.send_payload("application/json", json.dumps(payload, ensure_ascii=False).encode())
                    elif url.path.startswith("/image/"):
                        seq = int(url.path.removeprefix("/image/"))
                        with closing(sqlite3.connect(relay.path)) as db:
                            row = db.execute("SELECT jpg FROM alerts WHERE seq = ?", (seq,)).fetchone()
                        if row:
                            self.send_payload("image/jpeg", row[0])
                        else:
                            self.send_error(404)
                    else:
                        self.send_error(404)
                except (ValueError, OverflowError):
                    self.send_error(400)
                except sqlite3.Error:
                    self.send_error(503)
                except OSError:
                    pass

            def send_payload(self, mime, payload):
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.pending = Queue(maxsize=12)
        self.stop = Event()
        self.writer = Thread(target=self._write, daemon=True)
        self.worker = Thread(target=self.server.serve_forever, daemon=True)
        self.writer.start()
        self.worker.start()

    def submit(self, channel, source_kind, risk, frame):
        if self.stop.is_set():
            return False
        def rounded(value):
            return round(value, 1) if value is not None else None

        event = {"id": uuid4().hex, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                 "channel": channel, "source": source_kind, "level": "high", "reason": risk.reason,
                 "distance_m": rounded(risk.distance_m), "closing_kmh": rounded(risk.closing_kmh),
                 "speed_kmh": rounded(risk.speed_kmh), "ttc_s": rounded(risk.ttc_s)}
        try:
            self.pending.put_nowait((event, frame))
        except Full:
            return False
        return True

    def _write(self):
        with closing(sqlite3.connect(self.path)) as db:
            while not self.stop.is_set() or not self.pending.empty():
                try:
                    event, frame = self.pending.get(timeout=.25)
                except Empty:
                    continue
                try:
                    ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    if not ok:
                        raise OSError("cannot encode risk frame")
                    with db:
                        db.execute("INSERT INTO alerts(event, jpg) VALUES (?, ?)",
                                   (json.dumps(event, ensure_ascii=False), jpg.tobytes()))
                        db.execute("DELETE FROM alerts WHERE seq < "
                                   "COALESCE((SELECT seq FROM alerts ORDER BY seq DESC LIMIT 1 OFFSET 239), 0)")
                except (sqlite3.Error, OSError, cv2.error) as exc:
                    print(f"Alert snapshot failed: {exc}", flush=True)

    def close(self):
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.writer.join(timeout=2)


class DangerSnapshots:
    def __init__(self, relay, channel, live):
        self.relay, self.channel, self.live = relay, channel, live
        self.last_high = self.last_saved = float("-inf")

    def observe(self, risks, frame, now):
        high = min((risk for risk in risks if risk.level == HIGH),
                   key=lambda r: (float("inf") if r.ttc_s is None else r.ttc_s, r.distance_m),
                   default=None)
        if high is None:
            return
        new_episode = now-self.last_high >= 1.0
        self.last_high = now
        if new_episode or now-self.last_saved >= 6:
            if self.relay.submit(self.channel, "live" if self.live else "recording", high, frame):
                self.last_saved = now
