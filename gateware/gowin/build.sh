#!/bin/bash
# build.sh: the bring-up image in the fpga-tools container (fpc's tools/fpga-container/fpgarun, on a
# host with Docker or through ssh fpga): gowin/avb.tcl makes the project (and serdes.py the
# transceivers' register file), csr_result.py names that file in the project, gowin/run.tcl runs it.
# A test (GW_SRCS, GW_CST: no transceivers) runs in the first step.  GW_OUT, GW_DEVVER, GW_MODE pass through.
cd "$(dirname "$0")/.." || exit 1
fpgarun=${FPGARUN:-$HOME/devel/git/fpc/tools/fpga-container/fpgarun}
out=${GW_OUT:-$PWD/gowin/build/avb}
gw="env QT_QPA_PLATFORM=minimal LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libfreetype.so.6 GW_OUT=$out GW_DEVVER=$GW_DEVVER GW_MODE=$GW_MODE $HOME/tools/gowin-standard-1.9.12.04/IDE/bin/gw_sh"
if [ -n "$GW_CST" ]; then
    exec "$fpgarun" env GW_SRCS="$GW_SRCS" GW_CST="$GW_CST" $gw gowin/avb.tcl
fi
exec "$fpgarun" bash -c "$gw gowin/avb.tcl && python3 gowin/csr_result.py $out/avb/avb.gprj.user $out/serdes/serdes.csr && $gw gowin/run.tcl"
