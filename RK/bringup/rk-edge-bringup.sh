#!/bin/sh
set -eu
root=/home/linaro/sentry-vid007
driver=/sys/bus/platform/drivers/rk-pcie
controller=2a210000.pcie
dma=/dev/ANLOGIC-PCI0_c2h_0

case "$1" in
  prepare)
    if systemctl is-active --quiet sentry-vid007-display; then
        systemctl stop sentry-vid007-display
    fi
    if [ -e "$dma" ] && fuser "$dma"; then
        echo "The DMA device still has a reader" >&2
        exit 1
    fi
    if [ -d /sys/module/anlogic_pci_ring ]; then
        rmmod anlogic_pci_ring
    fi
    if [ -e "$driver/$controller" ]; then
        echo "$controller" > "$driver/unbind"
    fi
    exit 0
    ;;
  attach)
    if ! lspci -D -d 1edb:abcd | grep -q .; then
        if [ -e "$driver/$controller" ]; then
            echo "$controller" > "$driver/unbind"
        fi
        test -d /sys/class/gpio/gpio48 || echo 48 > /sys/class/gpio/export
        echo low > /sys/class/gpio/gpio48/direction
        sleep 0.15
        echo 1 > /sys/class/gpio/gpio48/value
        sleep 0.15
        echo "$controller" > "$driver/bind"
        for attempt in 1 2 3 4 5 6; do
            lspci -D -d 1edb:abcd | grep -q . && break
            sleep 2
        done
    fi
    ;;
esac

bdf=$(lspci -D -d 1edb:abcd | awk 'NR==1 {print $1}')
if [ -z "$bdf" ]; then
    echo "SENTRY endpoint did not enumerate" >&2
    dmesg | grep -E 'pcie.*(LTSSM|failed)' | tail -12 >&2
    exit 1
fi
bar="/sys/bus/pci/devices/$bdf/resource0"
cd "$root"

case "$1" in
  attach)
    setpci -s "$bdf" COMMAND=0006:0006
    if ! test -d /sys/module/anlogic_pci_ring; then
        insmod /root/aoi_tools/sgdma_ring_drv_fix/anlogic_pci_ring.ko poll_mode=1 enable_st_c2h_credit=1
    fi
    lspci -Dnn -s "$bdf"
    test -c "$dma"
    ;;
  benchmark)
    timeout 50s python3 -B capture.py --bar0 "$bar" --seconds 30 --output "$root/edge-frames"
    ;;
  display)
    systemd-run --unit=sentry-vid007-display --collect --setenv=DISPLAY=:0         --setenv=XAUTHORITY=/home/linaro/.Xauthority --setenv=QT_XCB_GL_INTEGRATION=none         --working-directory="$root" /usr/bin/python3 -B "$root/display.py"         --bar0 "$bar" --monitor 0 0 1680 1050 --snapshot "$root/edge-display.png"
    ;;
  *)
    echo "usage: $0 prepare|attach|benchmark|display" >&2
    exit 2
    ;;
esac
