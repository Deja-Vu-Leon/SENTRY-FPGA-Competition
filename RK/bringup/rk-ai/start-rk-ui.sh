#!/bin/bash
set -euo pipefail
cd /home/linaro/sentry-vid007/rk-ai
test "$(id -u)" = 0
install -d -m 0700 /run/sentry-vid007-ai
if systemctl is-active --quiet sentry-vid007-fasttone; then systemctl stop sentry-vid007-fasttone; fi
if [[ -e /run/sentry-vid007-ai/exchange ]]; then
    unlink /run/sentry-vid007-ai/exchange
fi
taskset -c 4,5 python3 -u four_camera.py "$@" &
inference=$!
preview=
cleanup() {
    if [[ -n "$preview" ]]; then
        kill -TERM "$preview" 2>/dev/null || true
        wait "$preview" 2>/dev/null || true
    fi
    kill -TERM "$inference" 2>/dev/null || true
    wait "$inference" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' TERM INT
for attempt in {1..50}; do
    kill -0 "$inference"
    if [[ -s /run/sentry-vid007-ai/exchange ]]; then break; fi
    sleep .1
done
test -s /run/sentry-vid007-ai/exchange
bash ../rk-ddr-hdmi.sh 0 ./rk-ai/vid007-rk-preview &
preview=$!
wait -n "$preview" "$inference"
