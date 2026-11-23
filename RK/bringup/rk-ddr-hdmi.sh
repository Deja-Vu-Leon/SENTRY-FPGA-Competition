#!/bin/bash
set -euo pipefail
cd /home/linaro/sentry-vid007
duration=${1:-120}
program=${2:-./vid007-ddr-kms}
if systemctl is-active --quiet sentry-vid007-display; then systemctl stop sentry-vid007-display; fi
if fuser /dev/ANLOGIC-PCI0_c2h_0; then
    echo 'DMA device still in use' >&2
    exit 1
fi
policy=/sys/devices/system/cpu/cpufreq/policy4/scaling_governor
original=$(cat "$policy")
restore() {
    echo "$original" > "$policy"
    systemctl start display-manager
}
trap restore EXIT
systemctl stop display-manager
echo performance > "$policy"
if [[ -d /sys/module/anlogic_pci_ring ]]; then rmmod anlogic_pci_ring; fi
insmod ./pcie-ring-batch/anlogic_pci_ring.ko poll_mode=1 enable_st_c2h_credit=1 c2h_batch=1
if (( duration == 0 )); then
    taskset -c 7 "$program" 0
else
    timeout -k 5 "$((duration+20))s" taskset -c 7 "$program" "$duration"
fi
