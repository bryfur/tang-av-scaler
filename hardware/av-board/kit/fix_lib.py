#!/usr/bin/env python3
"""Make every pin in lib/lcsc.kicad_sym passive.

EasyEDA's pin types are arbitrary (resistor arrays with "input" pins, regulator outputs as
"power_in"), which fills ERC with false errors; passive pins leave ERC checking connections.
Run by fetch_lib.sh after each fetch.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sexp import dump, parse  # noqa: E402

path = os.path.join(os.path.dirname(HERE), "lib", "lcsc.kicad_sym")
lib = parse(open(path).read())


def fix(x):
    for e in x:
        if isinstance(e, list) and e and e[0] == "pin":
            e[1] = "passive"
        elif isinstance(e, list):
            fix(e)


fix(lib)
open(path, "w").write(dump(lib) + "\n")
