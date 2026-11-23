#!/bin/bash
set -euo pipefail
cd /home/linaro/sentry-vid007/rk-ai
capture() {
    sudo -n timeout 7 ffmpeg -hide_banner -loglevel error -y -f kmsgrab \
        -device /dev/dri/card0 -plane_id 56 -i - -vf hwdownload,format=bgr0 \
        -frames:v 1 "rk-polished-$1.png"
}
sleep 6
capture transmission
sudo -n ./test-feature-key 2
sudo -n ./test-feature-key 7
sleep 6
capture processing
sudo -n ./test-feature-key 7
sudo -n ./test-feature-key 3
sleep 7
capture diagnostics
sudo -n ./test-feature-key 4
sleep 2
capture alerts
sudo -n ./test-feature-key 1
sleep 10
systemctl is-active sentry-vid007-ai
sudo -n journalctl -u sentry-vid007-ai --since '140 seconds ago' -o cat --no-pager |
    grep -E 'FPGA mode|HDMI KMS|DMA |infer_fps' | tail -37
