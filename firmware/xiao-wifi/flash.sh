#!/bin/bash
# flash.sh [c5|s3] [--port DEV] [--erase]: the firmware (build-esp32<chip>/, made on fpga by
# build.sh) into a XIAO over its USB, on the machine it is plugged into.  Only the first time:
# after it, updates go over Wi-Fi (tools/avx.py ota).
#
#   --port DEV   the XIAO's serial device; needed when more than one Espressif USB port
#                (303a:1001) is there: this script lists them
#   --erase      the whole flash first: the saved Wi-Fi network too
#
# A XIAO that does not answer: hold B (BOOT), tap R (RESET), let go, and run this again.
cd "$(dirname "$0")" || exit 1
chip=c5 port= erase=
while [ $# -gt 0 ]; do
    case $1 in
        c5|s3) chip=$1 ;;
        --port) port=$2; shift ;;
        --erase) erase=1 ;;
        *) sed -n '2,10p' "$0"; exit 2 ;;
    esac
    shift
done
build=build-esp32$chip
[ -f $build/flash_args ] || { echo "$build: not built (build.sh $chip, on fpga)"; exit 1; }
esptool=${ESPTOOL:-$HOME/tools/esptool-venv/bin/esptool}
if [ -z "$port" ]; then
    found=()
    for t in /sys/class/tty/ttyACM*; do
        [ -e "$t" ] || continue
        d=$(readlink -f "$t/device/..")
        [ "$(cat "$d/idVendor" 2> /dev/null)" = 303a ] && [ "$(cat "$d/idProduct" 2> /dev/null)" = 1001 ] &&
            found+=("/dev/$(basename "$t") $(cat "$d/serial" 2> /dev/null)")
    done
    case ${#found[@]} in
        0) echo "no XIAO (USB 303a:1001) found"; exit 1 ;;
        1) port=${found[0]%% *} ;;
        *) echo "more than one Espressif USB port: name the XIAO's with --port"; printf '  %s\n' "${found[@]}"; exit 1 ;;
    esac
fi
cd $build || exit 1
[ -n "$erase" ] && { "$esptool" --chip esp32$chip -p "$port" erase-flash || exit 1; }
exec "$esptool" --chip esp32$chip -p "$port" -b 460800 --before default-reset --after hard-reset \
    write-flash "@flash_args"
