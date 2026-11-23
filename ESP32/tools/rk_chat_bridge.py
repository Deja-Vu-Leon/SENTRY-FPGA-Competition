"""Serve HDMI F7 text requests through ESP32 in a separate process."""
import json
import logging
from pathlib import Path
import time

from gateway_client import Gateway, configured_token


ROOT = Path("/run/sentry-esp32")


def publish(text):
    temporary = ROOT / "answer.tmp"
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(ROOT / "answer.txt")


def main():
    logging.basicConfig(level=logging.INFO)
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    gateway = Gateway("http://192.168.50.1", configured_token())
    request = ROOT / "question.txt"
    while True:
        if request.exists():
            try:
                identifier, question = request.read_text(encoding="utf-8").split("\n", 1)
                publish("正在通过 ESP32 请求 DeepSeek，请稍候……")
                result = gateway.ask(question, identifier)
                publish(result["answer"])
                logging.info("HDMI chat completed %s upstream=%s", identifier, result.get("upstream_status"))
                (ROOT / "last-result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            except (OSError, ValueError, RuntimeError, TimeoutError) as error:
                publish("请求未完成，请检查热点和网关后重新提交。\n" + str(error))
                logging.warning("HDMI chat failed: %s", error)
            finally:
                request.unlink(missing_ok=True)
        time.sleep(.2)


if __name__ == "__main__":
    main()
