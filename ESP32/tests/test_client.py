"""Offline tests for the provided PC/RK client against a local protocol fixture."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

CLIENT = Path(__file__).resolve().parents[1] / "tools" / "gateway_client.py"
spec = importlib.util.spec_from_file_location("gateway_client", CLIENT)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class Fixture(BaseHTTPRequestHandler):
    jobs = {}
    events = {}
    images = {}

    def log_message(self, *_):
        pass

    def reply(self, code, value):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "image/jpeg" if isinstance(value, bytes) else "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def route(self):
        if self.headers.get("Authorization") != "Bearer test-token":
            return self.reply(401, {"error": "access_token_required"})
        payload = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.command == "POST" and self.path == "/v1/chat":
            job = json.loads(payload)
            if job["request_id"] in self.jobs and self.jobs[job["request_id"]]["question"] != job["question"]:
                return self.reply(409, {"error": "id_conflict"})
            self.jobs[job["request_id"]] = job
            return self.reply(202, {"request_id": job["request_id"], "state": "queued"})
        if self.command == "GET" and self.path.startswith("/v1/chat/"):
            key = self.path.split("/")[-1]
            if key not in self.jobs:
                return self.reply(404, {"error": "request_not_found"})
            return self.reply(200, {"request_id": key, "state": "done", "answer": "前方行人，请减速。"})
        if self.command == "POST" and self.path == "/v1/alerts":
            event = json.loads(payload)
            old = self.events.get(event["event_id"])
            if old is not None and old != event:
                return self.reply(409, {"error": "id_conflict"})
            self.events[event["event_id"]] = event
            return self.reply(201 if old is None else 200, event)
        if self.path.startswith("/v1/alerts/") and self.path.endswith("/image"):
            key = self.path.split("/")[-2]
            if self.command == "PUT":
                if key in self.images:
                    return self.reply(409, {"error": "image_already_stored"})
                self.images[key] = payload
                return self.reply(201, {"event_id": key, "has_image": True})
            if self.command == "GET" and key in self.images:
                return self.reply(200, self.images[key])
        return self.reply(404, {"error": "endpoint_not_found"})

    do_GET = do_POST = do_PUT = route


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        Fixture.jobs.clear()
        Fixture.events.clear()
        Fixture.images.clear()
        self.gateway = client.Gateway(self.url, "test-token")

    @patch.object(client.time, "sleep", return_value=None)
    def test_utf8_chat_and_poll(self, _):
        result = self.gateway.ask("前方行人怎么办？", "question-1")
        self.assertEqual(result["answer"], "前方行人，请减速。")
        self.assertEqual(Fixture.jobs["question-1"]["question"], "前方行人怎么办？")

    @patch.object(client.time, "sleep", return_value=None)
    def test_request_id_conflict(self, _):
        self.gateway.ask("first", "same-id")
        with self.assertRaisesRegex(RuntimeError, "409"):
            self.gateway.ask("different", "same-id")

    def test_bad_authorization(self):
        with self.assertRaisesRegex(RuntimeError, "401"):
            client.Gateway(self.url, "wrong").request("GET", "/v1/alerts")

    def test_alarm_image_retry_and_conflict(self):
        metadata = {"event_id": "B01-1", "camera": "B01", "reason": "疑似滑坡源区",
                    "event_time": "2026-11-18T10:30:00+08:00", "confidence": .93}
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "fixture.jpg"
            image.write_bytes(b"\xff\xd8protocol-fixture\xff\xd9")
            self.gateway.alert(metadata, image)
            self.gateway.alert(metadata, image)
            self.assertEqual(len(Fixture.events), 1)
            self.assertEqual(Fixture.images["B01-1"], image.read_bytes())
            image.write_bytes(b"\xff\xd8different\xff\xd9")
            with self.assertRaisesRegex(RuntimeError, "different image"):
                self.gateway.alert(metadata, image)
            self.assertEqual(Fixture.events["B01-1"]["event_time"], metadata["event_time"])

    def test_invalid_image_is_rejected_before_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "bad.jpg"
            image.write_bytes(b"wrong format")
            with self.assertRaises(ValueError):
                self.gateway.alert({"event_id": "B02-1"}, image)
            self.assertFalse(Fixture.events)

    def test_large_snapshot_is_preserved(self):
        metadata = {"event_id": "A01-large", "camera": "A01", "reason": "前方障碍物",
                    "event_time": "2026-11-18T11:30:00+08:00"}
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "large.jpg"
            data = b"\xff\xd8" + b"x" * (1024 * 1024) + b"\xff\xd9"
            image.write_bytes(data)
            self.gateway.alert(metadata, image)
            self.assertEqual(Fixture.images["A01-large"], data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
