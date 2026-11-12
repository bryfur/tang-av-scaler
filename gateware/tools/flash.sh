#!/bin/bash
# flash.sh [FS]: the bitstream into the SOM's configuration flash (the FPGA loads it by itself at
# power-on, in about 20 s; the XIAO's link then brings the board up), over the XIAO's USB-JTAG
# bridge, verified.  The picture stops while it is written (2 minutes) and comes back by itself.
#   flash.sh --backup FILE    the flash's 16 MB read into FILE first (4 minutes)
# Reading or writing the flash clears the FPGA: after a --backup alone, load.sh brings it back.
ofl=${OFL:-$HOME/tools/ofl/bin/openFPGALoader}
if [ "$1" = --backup ]; then
    exec "$ofl" -c esp32s3 --dump-flash --file-size 16777216 -o 0 "${2:?a file to write}"
fi
fs=${1:-$(dirname "$0")/../gowin/build/avb/avb/impl/pnr/avb.fs}
exec "$ofl" -c esp32s3 -f --verify "$fs"
