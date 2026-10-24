#!/bin/sh
# Fetch the LCSC parts' symbols, footprints and 3D models into lib/ (easyeda2kicad, in a venv
# at ~/tools/eda-venv), then bring them up to KiCad 9's format. The symbols and footprints are
# committed; the 3D models are not (60 MB), so run this once after cloning for 3D views.
set -e
cd "$(dirname "$0")"
EDA=${EDA:-$HOME/tools/eda-venv/bin/easyeda2kicad}
# HDMI-001, RCJ-014, RCJ-011, crystal, NFE61PT, 2x20 TH and SMD sockets, TPS7A7001, 10 uH,
# PTC, ADV7842, ADV7511, PCM1808, TLV62569, TPD4E05U06, EZAEG2A50AX, 33 uF tantalum,
# 75 R and 4.7 k arrays, 2.2 uH (RCJ-012 has no EasyEDA model: it shares RCJ-011's footprint)
"$EDA" --full --output lib/lcsc --overwrite --lcsc_id C138388 C4991844 C4992678 C362486 C79933 \
    C5124634 C22436166 C60719 C222882 C883105 C514382 C179459 C55513 C141836 C138714 C242174 \
    C7202 C39128 C29586 C167747
kicad-cli sym upgrade --force lib/lcsc.kicad_sym
kicad-cli fp upgrade --force lib/lcsc.pretty
python3 fix_lib.py
