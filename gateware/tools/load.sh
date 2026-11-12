#!/bin/bash
# load.sh [FS]: a bitstream into the FPGA's SRAM (nothing flashed: a power cycle or RECONFIG brings
# the flash's image back) over the XIAO's USB-JTAG bridge.  The .fs, not compressed: openFPGALoader
# 1.1.1 cannot parse a compressed one, and it sends a .bin in the wrong bit order ("Bad Command").
fs=${1:-$(dirname "$0")/../gowin/build/avb/avb/impl/pnr/avb.fs}
ofl=${OFL:-$HOME/tools/ofl/bin/openFPGALoader}
log=$(mktemp)
t0=$(date +%s)
"$ofl" -c esp32s3 --verbose-level 1 "$fs" > "$log" 2>&1
rc=$?
st=$(tr '\r' '\n' < "$log" | grep -a "after program sram" | tail -1 | awk '{print $NF}')
echo "load: rc $rc, $(( $(date +%s) - t0 )) s, status ${st:-?}"
# Done Final without Bad Command, CRC or ID errors
case $st in
    "") tr '\r' '\n' < "$log" | grep -a -v "Load SRAM" | tail -5; rc=1 ;;
    *) v=$((16#$st)); if [ $(( v & 0x2000 )) -eq 0 ] || [ $(( v & 0x0B )) -ne 0 ]; then
           tr '\r' '\n' < "$log" | grep -a -A8 "after program sram" | tail -9; rc=1; fi ;;
esac
rm -f "$log"
exit $rc
