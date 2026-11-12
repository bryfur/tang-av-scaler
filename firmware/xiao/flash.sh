#!/bin/bash
# flash.sh [--wait SECONDS]: the firmware (build/, made on fpga by `idf.py build`) into the XIAO
# ESP32-S3 over its USB, on the machine it is plugged into.  A XIAO running this firmware (or a
# blank one) is reset into its loader over USB; one running something else on TinyUSB needs
# B (BOOT) held while R (RESET) is tapped once: --wait waits that long for it to show up.
cd "$(dirname "$0")/build" || exit 1
wait=0
[ "$1" = --wait ] && wait=$2
esptool=${ESPTOOL:-$HOME/tools/esptool-venv/bin/esptool}
find_port() {
    for t in /sys/class/tty/ttyACM*; do
        [ -e "$t" ] || continue
        d=$(readlink -f "$t/device/..")
        if [ "$(cat "$d/idVendor" 2>/dev/null)" = 303a ] && [ "$(cat "$d/idProduct" 2>/dev/null)" = 1001 ]; then
            echo "/dev/$(basename "$t")"; return 0
        fi
    done
    return 1
}
t0=$(date +%s)
until port=$(find_port); do
    [ $(( $(date +%s) - t0 )) -ge "$wait" ] && { echo "no XIAO (USB 303a:1001) found"; exit 1; }
    sleep 0.5
done
sleep 1
exec "$esptool" --chip esp32s3 -p "$port" -b 460800 --before default-reset --after watchdog-reset \
    write-flash --flash-mode dio --flash-freq 80m --flash-size 8MB \
    0x0 bootloader/bootloader.bin 0x8000 partition_table/partition-table.bin 0x10000 avxiao.bin
