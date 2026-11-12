#!/bin/bash
# run.sh [FS]: the firmware's XVC server and its own scans on a PC against a model of the FPGA's
# TAP (xvc_model.c), with openFPGALoader as the client: its detect, and with FS a whole SRAM load.
# Needs gcc and openFPGALoader (OFL) on the same machine, or MODEL_HOST: a machine with gcc that
# shares this directory (ssh), the model run there.
cd "$(dirname "$0")" || exit 1
ofl=${OFL:-$HOME/tools/ofl/bin/openFPGALoader}
port=25420
on() { if [ -n "$MODEL_HOST" ]; then ssh "$MODEL_HOST" "cd $PWD && $*"; else eval "$*"; fi; }
on "mkdir -p build && gcc -O2 -Wall -Wextra -I../main -o build/xvc_model xvc_model.c ../main/xvc_core.c ../main/tap.c" || exit 1
on "build/xvc_model self" || { echo "FAIL: the firmware's own scans"; exit 1; }
on "timeout 300 build/xvc_model $port" > build/model.log 2>&1 &
sleep 1
ip=127.0.0.1
[ -n "$MODEL_HOST" ] && ip=$(getent hosts "$MODEL_HOST" | awk '{print $1; exit}')
rc=0
"$ofl" -c xvc-client --ip "$ip" --port $port --detect 2>&1 | grep -q "GW5AST-138" && echo "detect: GW5AST-138" ||
    { echo "FAIL: detect"; rc=1; }
if [ -n "$1" ]; then
    t0=$(date +%s)
    "$ofl" -c xvc-client --ip "$ip" --port $port "$1" 2>&1 | tr '\r' '\n' | grep -a -E "DONE|FAIL|rror" | sort | uniq -c
    echo "load: $(( $(date +%s) - t0 )) s"
fi
sleep 1
on "pkill -f 'build/xvc_model $port'" 2> /dev/null
cat build/model.log
[ -n "$1" ] && { grep -q "status 0003f0[0-9a-f][0-9a-f]" build/model.log && echo "load: DONE in the model" || { echo "FAIL: load"; rc=1; }; }
exit $rc
