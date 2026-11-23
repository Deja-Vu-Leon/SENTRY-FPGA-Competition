#!/bin/bash
set -euo pipefail
cd /home/linaro/sentry-vid007/rk-ai
test "$(id -u)" = 0
install -d -m 0700 /run/sentry-vid007-ai
if systemctl is-active --quiet sentry-vid007-fasttone; then systemctl stop sentry-vid007-fasttone; fi
if [[ -e /run/sentry-vid007-ai/exchange ]]; then
    unlink /run/sentry-vid007-ai/exchange
fi
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 0-3 python3 -u cockpit_worker.py "$@" &
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
for attempt in {1..200}; do
    if ! kill -0 "$inference" 2>/dev/null; then
        echo 'RK inference exited before creating the frame exchange' >&2
        wait "$inference"
        exit 1
    fi
    if [[ -s /run/sentry-vid007-ai/exchange ]]; then break; fi
    sleep .1
done
if ! test -s /run/sentry-vid007-ai/exchange; then
    echo 'Timed out waiting for the RK frame exchange' >&2
    exit 1
fi
bash ../rk-ddr-hdmi.sh 0 ./rk-ai/vid007-cockpit-preview &
preview=$!
status=0
wait -n "$preview" "$inference" || status=$?
if [[ $status == 75 ]]; then
    echo 'Recovering the FPGA PCIe controller after losing BAR access' >&2
    bash ../rk-edge-bringup.sh prepare && bash ../rk-edge-bringup.sh attach
fi
exit "$status"
