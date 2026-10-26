#!/usr/bin/env python3
"""Fetch the 3D models of the KiCad library footprints the revisions use (resistors, capacitors,
diodes...) into lib/kicad.3dshapes, from KiCad's packages3D repository: for 3D renders
(kit/render.py) where KiCad's own model library is not installed. The LCSC parts' models come with
fetch_lib.sh. Neither is in git.

    python3 kit/fetch_3d.py
"""
import os
import re
import sys
import urllib.request

KIT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(KIT)
OUT = os.path.join(ROOT, "lib", "kicad.3dshapes")
SYSFP = "/usr/share/kicad/footprints"
URL = "https://gitlab.com/kicad/libraries/kicad-packages3D/-/raw/master/%s"


def used_footprints():
    """Every non-LCSC footprint any revision's board.py names."""
    out = set()
    for d in sorted(os.listdir(ROOT)):
        if d.startswith("rev-") and os.path.isfile(os.path.join(ROOT, d, "board.py")):
            src = open(os.path.join(ROOT, d, "board.py")).read()
            out |= set(re.findall(r'"((?!lcsc:)[A-Za-z_]+:[^"]+)"', src))
    # the parts library's two-pin kinds (kit/parts.py TWO) and rev C's shared circuit
    for f in (os.path.join(KIT, "parts.py"), os.path.join(ROOT, "rev-c", "carrier.py")):
        if os.path.exists(f):
            out |= set(re.findall(r'"((?!lcsc:)(?:Resistor_SMD|Capacitor_SMD|Inductor_SMD|Diode_SMD|Fuse|Package_TO_SOT_SMD|MountingHole):[^"]+)"', open(f).read()))
    return sorted(f for f in out if os.path.isfile(os.path.join(SYSFP, f.split(":")[0] + ".pretty", f.split(":")[1] + ".kicad_mod")))


def main():
    n = 0
    for fp in used_footprints():
        lib, name = fp.split(":")
        mod = open(os.path.join(SYSFP, lib + ".pretty", name + ".kicad_mod")).read()
        for path in re.findall(r'\(model "\$\{KICAD\d*_3DMODEL_DIR\}/([^"]+)"', mod):
            dst = os.path.join(OUT, path)
            if os.path.exists(dst):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                urllib.request.urlretrieve(URL % path, dst)
                n += 1
                print(path)
            except Exception as e:                  # (some footprints name a model KiCad never made)
                print("%s: %s" % (path, e), file=sys.stderr)
    print("%d models fetched into %s" % (n, OUT))


if __name__ == "__main__":
    main()
