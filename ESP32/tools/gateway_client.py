"""HTTP client for PC checks and later FPGA/SoC network integration."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def configured_token():
    token = os.environ.get("SENTRY_ACCESS_TOKEN")
    if not token and os.name == "posix" and os.geteuid() == 0:
        try:
            token = Path("/etc/sentry-esp32/access-token").read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            pass
    return token


class Gateway:
    def __init__(self, base_url, token, timeout=30):
        if not token:
            raise ValueError("Set SENTRY_ACCESS_TOKEN or supply an explicit access token")
        self.base = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(self, method, path, body=None, content_type="application/json"):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base + path, data=body, method=method,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": content_type})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = response.read()
                return json.loads(data) if response.headers.get_content_type() == "application/json" else data
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {error.code}: {detail}") from error

    def ask(self, question, request_id=None, timeout=240):
        request_id = request_id or uuid.uuid4().hex
        result = self.request("POST", "/v1/chat", {"request_id": request_id, "question": question})
        end = time.monotonic() + timeout
        while result["state"] in ("queued", "running"):
            if time.monotonic() >= end:
                raise TimeoutError(f"request pending: {request_id}")
            time.sleep(1)
            result = self.request("GET", "/v1/chat/" + urllib.parse.quote(request_id, safe=""))
        if result["state"] != "done":
            raise RuntimeError(f'{result.get("error", "chat failed")} (request {request_id})')
        return result

    def alert(self, metadata, image):
        data = image.read_bytes()
        if len(data) > 2 * 1024 * 1024 or not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
            raise ValueError("image must be a JPEG of at most 2 MiB")
        result = self.request("POST", "/v1/alerts", metadata)
        path = "/v1/alerts/" + urllib.parse.quote(metadata["event_id"], safe="") + "/image"
        try:
            return self.request("PUT", path, data, "image/jpeg")
        except RuntimeError as error:
            if "HTTP 409:" not in str(error):
                raise
            if self.request("GET", path) != data:
                raise RuntimeError("event already has a different image") from error
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://192.168.50.1")
    parser.add_argument("--token", default=None)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("status")
    actions.add_parser("events")
    actions.add_parser("restart")
    ask = actions.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--request-id")
    settings = actions.add_parser("configure")
    settings.add_argument("file", type=Path)
    alert = actions.add_parser("alert")
    alert.add_argument("metadata", type=Path)
    alert.add_argument("image", type=Path)
    args = parser.parse_args()
    gateway = Gateway(args.url, args.token or configured_token())
    if args.action == "status":
        result = gateway.request("GET", "/v1/status")
    elif args.action == "events":
        result = gateway.request("GET", "/v1/alerts")
    elif args.action == "ask":
        result = gateway.ask(args.question, args.request_id)
    elif args.action == "configure":
        result = gateway.request("POST", "/v1/settings", json.loads(args.file.read_text(encoding="utf-8")))
    elif args.action == "restart":
        result = gateway.request("POST", "/v1/restart", {})
    else:
        result = gateway.alert(json.loads(args.metadata.read_text(encoding="utf-8")), args.image)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
