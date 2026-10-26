#!/bin/sh
# Fetch the LCSC parts' symbols, footprints and 3D models into lib/ (easyeda2kicad, in a venv
# at ~/tools/eda-venv), then bring them up to KiCad 9's format. The symbols and footprints are
# committed; the 3D models are not (60 MB), so run this once after cloning for 3D views.
set -e
cd "$(dirname "$0")/.."
EDA=${EDA:-$HOME/tools/eda-venv/bin/easyeda2kicad}
# HDMI-001, RCJ-014, RCJ-011, crystal, NFE61PT, the 2x20 socket, TPS7A7001, 10 uH, PTC, ADV7842,
# ADV7511, PCM1808, TLV62569, TPD4E05U06, 33 uF tantalum, the 75 R array, 2.2 uH, the TS-1187A
# button, ADV7181D (rev B) (RCJ-012 has no EasyEDA model: it shares RCJ-011's footprint); rev B's
# later parts: the YXC crystal, TPS7A2045, the SYNC and S/PDIF headers, the LED, the XIAO sockets,
# the S/PDIF inverters, the VGA header, its sync buffer, the XIAO's level translators; rev C's SOM
# connector, USB-C, MS5351M, its crystal and LDOs, SN65DP159, the JTAG and optical headers, the
# orange RCA, the 2N7002; the video inputs single-line TPD1E05U06
"$EDA" --full --output lib/lcsc --overwrite --lcsc_id C138388 C4991844 C4992678 C362486 C79933 \
    C5124634 C60719 C222882 C883105 C514382 C179459 C55513 C141836 C138714 \
    C7202 C39128 C167747 C318884 C514378 C112564 C2873627 C492401 C2286 C22438157 C492404 \
    C81934 C7827 C68234 C10429 C27643 C81461 C424649 C165948 C1509083 C5265839 C403651 C179676 \
    C492405 C2937625 C22359757 C194395 C8545 C436349
# the DF40HC 80-pin connector's symbol is called "DF40HC" like the 100-pin one: fetched apart, merged
# in as DF40HC-80DS
T=$(mktemp -d)
"$EDA" --symbol --footprint --output "$T/x" --overwrite --lcsc_id C2858577
cp "$T"/x.pretty/*.kicad_mod lib/lcsc.pretty/
python3 kit/merge_sym.py "$T/x.kicad_sym" DF40HC DF40HC-80DS
rm -r "$T"
kicad-cli sym upgrade --force lib/lcsc.kicad_sym
kicad-cli fp upgrade --force lib/lcsc.pretty
python3 kit/fix_lib.py
