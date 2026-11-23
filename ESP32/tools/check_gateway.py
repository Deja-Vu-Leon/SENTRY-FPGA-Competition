"""RK-side gateway readiness and optional real DeepSeek connectivity check."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from gateway_client import Gateway, configured_token


def status_failures(status):
    checks = [(21, status.get("ethernet_link"), "ESP32 网口无链路，请检查 ESP32 与板卡网线"),
              (22, status.get("wifi_online"), "ESP32 未连接手机热点，请打开 2.4 GHz 热点并检查名称和密码"),
              (23, status.get("clock_ready"), "ESP32 尚未完成网络校时，HTTPS 暂不可用"),
              (24, status.get("api_key_configured"), "ESP32 未配置 DeepSeek API Key")]
    return [(code, message) for code, passed, message in checks if not passed]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://192.168.50.1")
    parser.add_argument("--full", action="store_true", help="Make one real DeepSeek request")
    parser.add_argument("--device-only", action="store_true", help="Skip RK-specific service and IME checks")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    gateway = Gateway(args.url, configured_token(), timeout=8)
    report = dict(passed=False, checks=[], failures=[], api_test="not_requested")
    failures = []
    try:
        status = gateway.request("GET", "/v1/status")
        report["status"] = status
        print("[OK] ESP32 已启动，运行 %.0f 秒" % status.get("uptime_seconds", 0))
        failures.extend(status_failures(status))
        print("[ESP32_URL] http://" + status.get("wifi_ip", "0.0.0.0"))
    except (OSError, ValueError, RuntimeError) as error:
        failures.append((20, "ESP32 无响应，请确认已上电、网线连接正常及直连 IP 配置正确：" + str(error)))
    if not args.device_only:
        units = ["sentry-esp32-alerts", "sentry-esp32-chat"]
        for unit in units:
            result = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=8)
            report["checks"].append(dict(service=unit, state=result.stdout.strip()))
            if result.returncode:
                failures.append((25, "RK 后台服务未运行：" + unit))
        dictionary = Path("/home/linaro/sentry-esp32/ime/dict_pinyin.dat")
        binary = Path("/home/linaro/sentry-vid007/rk-ai/vid007-cockpit-preview")
        if not dictionary.exists() or not binary.exists() or b"sentry_ime_init\0" not in binary.read_bytes():
            failures.append((27, "RK 中文输入组件缺失，请重新部署 RK 中文输入版本"))
    if not failures and args.full:
        try:
            identifier = "bootcheck-" + str(time.time_ns())
            response = gateway.ask("这是设备启动联网自检，请只回复：连接正常。", identifier, timeout=90)
            report["api_test"] = dict(state=response["state"], upstream_status=response.get("upstream_status"),
                                      answer=response.get("answer"))
            if response.get("upstream_status") != 200:
                raise RuntimeError("DeepSeek HTTP status is not 200")
            print("[OK] DeepSeek 实际请求成功，HTTP 200")
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            failures.append((26, "DeepSeek 请求失败，请检查热点互联网、API 额度和密钥：" + str(error)))
    report["failures"] = [dict(code=code, reason=message) for code, message in failures]
    report["passed"] = not failures
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for _, message in failures:
        print("[ERROR] " + message)
    if not failures:
        print("[OK] 网关启动、热点、校时、API 配置及所选 RK 检查全部通过")
    return failures[0][0] if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("[ERROR] 网关检查程序异常：" + str(error))
        sys.exit(29)
