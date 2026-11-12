#!/bin/bash
# build.sh [c5|s3]...: the firmware for a XIAO ESP32-C5 (default) or ESP32-S3, on fpga (ESP-IDF
# 6.x: ~/esp/env.sh).  Each chip has its own build directory, build-<chip>/, with its sdkconfig
# (made from sdkconfig.defaults: after a change there, delete build-*/sdkconfig).
cd "$(dirname "$0")" || exit 1
# (the scaler's CPU's program goes into the firmware: gateware/sw)
make -C ../../gateware/sw > /dev/null || { echo "gateware/sw: make failed"; exit 1; }
. "$HOME/esp/env.sh" > /dev/null || exit 1
[ $# -eq 0 ] && set -- c5
rc=0
for t in "$@"; do
    case $t in c5|s3) ;; *) sed -n '2,4p' "$0"; exit 2 ;; esac
    b=build-esp32$t
    if [ ! -f $b/sdkconfig ]; then
        idf.py -B $b -D SDKCONFIG=$b/sdkconfig set-target esp32$t > /dev/null 2>&1 ||
            { echo "$t: set-target failed"; rc=1; continue; }
    fi
    if idf.py -B $b -D SDKCONFIG=$b/sdkconfig build > $b/build.log 2>&1; then
        printf "%-3s %s\n" "$t" "$(grep -o 'avwifi.bin binary size.*free.' $b/build.log | tail -1)"
    else
        echo "$t: build failed, see $b/build.log"; grep -m8 -E "error|Error" $b/build.log; rc=1
    fi
done
exit $rc
