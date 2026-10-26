#!/usr/bin/env python3
"""Copy one symbol from another library into lib/lcsc.kicad_sym under a new name (replacing a symbol
of that name). For parts whose EasyEDA symbol name clashes with one already there (the DF40HC
80- and 100-pin connectors are both "DF40HC").

    python3 kit/merge_sym.py SOURCE.kicad_sym NAME NEW_NAME
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sexp import Quoted, dump, parse  # noqa: E402

src, name, new = sys.argv[1:4]
path = os.path.join(os.path.dirname(HERE), "lib", "lcsc.kicad_sym")
lib = parse(open(path).read())
sym = [e for e in parse(open(src).read()) if isinstance(e, list) and e[:2] == ["symbol", name]][0]


def rename(x):
    # the symbol and its units ("NAME_0_1", "NAME_1_1"), and its Value property
    for i, e in enumerate(x):
        if isinstance(e, Quoted) and (e == name or e.startswith(name + "_")):
            x[i] = Quoted(new + e[len(name):])
        elif isinstance(e, list):
            rename(e)


rename(sym)
lib[:] = [e for e in lib if not (isinstance(e, list) and e[:2] == ["symbol", new])] + [sym]
open(path, "w").write(dump(lib) + "\n")
print("%s: %s from %s" % (path, new, src))
