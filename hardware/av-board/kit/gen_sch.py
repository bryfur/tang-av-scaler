#!/usr/bin/env python3
"""Write a revision's schematic (<name>.kicad_sch) from its board.py.

The schematic is generated, not drawn: each symbol unit is placed in its block's area, and every
pin gets a short wire and a label with its net's name (KiCad connects equal labels), or a
no-connect flag. A PWR_FLAG sits on every net that has a power-input pin and no power output, as
the regulators' outputs here are plain pins. Open it in KiCad to read it, run ERC with
kicad-cli; change the board in board.py, not here.

    python3 kit/gen_sch.py rev-b     # rev-b/<name>.kicad_sch (+ .kicad_pro, sym-lib-table, fp-lib-table)
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rev  # noqa: E402
from sexp import Quoted, dump, find, findall, parse, q  # noqa: E402

board = rev.board(rev.args(__doc__)[0])
HERE = rev.rev_dir(sys.argv[1])
LIB = os.path.join(rev.ROOT, "lib")
NAME = board.NAME
SYSLIB = "/usr/share/kicad/symbols"
GRID = 1.27
STUB = 2.54


def uid(*key):
    return Quoted(str(uuid.uuid5(uuid.NAMESPACE_URL, "tang-av-scaler/" + "/".join(map(str, key)))))


ROOT = uid("root")

# ---------------------------------------------------------------------------
# Library symbols
# ---------------------------------------------------------------------------

_libs = {}


def load_symbol(lib_id):
    lib, name = lib_id.split(":")
    if lib not in _libs:
        path = os.path.join(LIB, "lcsc.kicad_sym") if lib == "lcsc" else os.path.join(SYSLIB, lib + ".kicad_sym")
        _libs[lib] = {s[1]: s for s in findall(parse(open(path).read()), "symbol")}
    sym = _libs[lib][name]
    assert not find(sym, "extends"), lib_id
    out = [sym[0], q(lib_id)] + sym[2:]
    return out


def pins_of(sym):
    """[(unit, number, name, x, y, angle, type)] of a library symbol (unit 0 = all units)."""
    out = []
    for sub in findall(sym, "symbol"):
        unit = int(str(sub[1]).rsplit("_", 2)[1])
        for p in findall(sub, "pin"):
            at = find(p, "at")
            out.append((unit, str(find(p, "number")[1]), str(find(p, "name")[1]), float(at[1]), float(at[2]),
                        int(float(at[3])) if len(at) > 3 else 0, p[1]))
    return out


def units_of(sym):
    return sorted({u for u, *_ in pins_of(sym)} - {0}) or [1]


def extent(sym, unit):
    xs, ys = [], []
    for u, _n, _nm, x, y, a, _t in pins_of(sym):
        if u in (0, unit):
            xs.append(x)
            ys.append(y)
    for sub in findall(sym, "symbol"):
        if int(str(sub[1]).rsplit("_", 2)[1]) not in (0, unit):
            continue
        for g in findall(sub, "rectangle"):
            for k in ("start", "end"):
                xs.append(float(find(g, k)[1]))
                ys.append(float(find(g, k)[2]))
    return min(xs), max(xs), min(ys), max(ys)


def snap(v):
    return round(v / GRID) * GRID


# ---------------------------------------------------------------------------
# Placement: blocks side by side, parts in rows within a block
# ---------------------------------------------------------------------------

BLOCK_W = {"headers": 260, "power": 330, "adv7842": 420, "pcm1808": 200, "adv7511": 330}


def layout():
    placed = []                 # (part, unit, x, y)
    x0 = 20.0
    blocks = []
    for p in board.PARTS:
        if p.block not in blocks:
            blocks.append(p.block)
    height = 0
    for b in blocks:
        w = BLOCK_W.get(b, 250)
        x, y, row_h = x0, 30.0, 0
        parts = [p for p in board.PARTS if p.block == b]
        # big parts first, then the rest in the order written
        parts.sort(key=lambda p: -len(p.pins) if len(p.pins) > 8 else 0)
        for p in parts:
            sym = load_symbol(p.symbol)
            for unit in units_of(sym):
                xmin, xmax, ymin, ymax = extent(sym, unit)
                lw = max([len(n) for n in p.pins.values()] + [4]) * 1.0 + STUB + 4
                bw = (xmax - xmin) + 2 * lw
                bh = (ymax - ymin) + 12
                if x + bw > x0 + w and x > x0:
                    x, y = x0, y + row_h
                    row_h = 0
                cx = snap(x + lw - xmin)
                cy = snap(y + 6 + ymax)
                placed.append((p, unit, cx, cy))
                x += bw
                row_h = max(row_h, bh)
        height = max(height, y + row_h)
        x0 += w + 20
    return placed, x0, height + 20


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def prop(name, value, x, y, hide=False, angle=0):
    e = ["property", q(name), q(value), ["at", x, y, angle], ["effects", ["font", ["size", 1.27, 1.27]]] +
         ([["hide", "yes"]] if hide else [])]
    return e


def label(net, x, y, angle):
    just = {0: "left", 90: "left", 180: "right", 270: "right"}[angle]
    return ["label", q(net), ["at", x, y, angle], ["fields_autoplaced", "yes"],
            ["effects", ["font", ["size", 1.27, 1.27]], ["justify", just]], ["uuid", uid("lab", net, x, y)]]


def main():
    placed, W, H = layout()
    lib_ids = []
    for p in board.PARTS:
        if p.symbol not in lib_ids:
            lib_ids.append(p.symbol)
    lib_ids.append("power:PWR_FLAG")
    items = []
    power_in, power_out = set(), set()
    for p, unit, cx, cy in placed:
        sym = load_symbol(p.symbol)
        inst = ["symbol", ["lib_id", q(p.symbol)], ["at", cx, cy, 0], ["unit", unit],
                ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "yes" if p.dnp else "no"],
                ["fields_autoplaced", "yes"], ["uuid", uid("sym", p.ref, unit)]]
        xmin, xmax, ymin, ymax = extent(sym, unit)
        inst.append(prop("Reference", p.ref, cx, snap(cy - ymax - 3.81)))
        inst.append(prop("Value", p.value, cx, snap(cy - ymin + 3.81)))
        inst.append(prop("Footprint", p.footprint, cx, cy, hide=True))
        inst.append(prop("Datasheet", "", cx, cy, hide=True))
        inst.append(prop("LCSC", p.lcsc, cx, cy, hide=True))
        if p.note:
            inst.append(prop("Note", p.note, cx, cy, hide=True))
        for u, num, _nm, x, y, a, typ in pins_of(sym):
            if u not in (0, unit):
                continue
            inst.append(["pin", q(num), ["uuid", uid("pin", p.ref, unit, num)]])
            px, py = cx + x, cy - y
            # the pin's angle points from its end into the body; outward is the other way
            dx, dy = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[a]
            net = p.pins.get(num)
            if net is None:
                items.append(["no_connect", ["at", px, py], ["uuid", uid("nc", p.ref, num)]])
                continue
            ex, ey = px + dx * STUB, py + dy * STUB
            items.append(["wire", ["pts", ["xy", px, py], ["xy", ex, ey]], ["stroke", ["width", 0], ["type", "default"]],
                          ["uuid", uid("w", p.ref, unit, num)]])
            items.append(label(net, ex, ey, {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(dx, dy)]))
            if typ == "power_in":
                power_in.add(net)
            if typ == "power_out":
                power_out.add(net)
        inst.append(["instances", ["project", q(NAME), ["path", q("/" + ROOT), ["reference", q(p.ref)], ["unit", unit]]]])
        items.append(inst)
    # PWR_FLAGs: a row along the bottom
    fx, fy = 20.0, snap(H + 10)
    for k, net in enumerate(sorted(power_in - power_out)):
        x = snap(fx + (k % 20) * 25.4)
        y = snap(fy + (k // 20) * 15.24)
        ref = "#FLG%02d" % (k + 1)
        items.append(["symbol", ["lib_id", q("power:PWR_FLAG")], ["at", x, y, 0], ["unit", 1],
                      ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"],
                      ["uuid", uid("flag", net)],
                      prop("Reference", ref, x, y - 6.35, hide=True), prop("Value", "PWR_FLAG", x, y - 3.81),
                      prop("Footprint", "", x, y, hide=True), prop("Datasheet", "", x, y, hide=True),
                      ["pin", q("1"), ["uuid", uid("flagpin", net)]],
                      ["instances", ["project", q(NAME), ["path", q("/" + ROOT), ["reference", q(ref)], ["unit", 1]]]]])
        items.append(["wire", ["pts", ["xy", x, y], ["xy", x, y + STUB]], ["stroke", ["width", 0], ["type", "default"]],
                      ["uuid", uid("fw", net)]])
        items.append(label(net, x, y + STUB, 270))
    H = fy + 40
    sch = ["kicad_sch", ["version", 20250114], ["generator", q("gen_sch.py")], ["generator_version", q("9.0")],
           ["uuid", ROOT], ["paper", q("User"), round(W), round(H)],
           ["title_block", ["title", q("Tang Console AV board rev " + board.REV)], ["company", q("tang-av-scaler")],
            ["comment", 1, q("Generated by gen_sch.py from board.py: edit board.py, not this file")]],
           ["lib_symbols"] + [load_symbol(i) for i in lib_ids]] + items + \
          [["sheet_instances", ["path", q("/"), ["page", q("1")]]], ["embedded_fonts", "no"]]
    with open(os.path.join(HERE, NAME + ".kicad_sch"), "w") as f:
        f.write(dump(sch) + "\n")
    # (KiCad's own libraries the board uses, after Device and power)
    more = sorted({i.split(":")[0] for i in lib_ids} - {"lcsc", "Device", "power"})
    with open(os.path.join(HERE, "sym-lib-table"), "w") as f:
        f.write('(sym_lib_table\n  (version 7)\n'
                '  (lib (name "lcsc")(type "KiCad")(uri "${KIPRJMOD}/../lib/lcsc.kicad_sym")(options "")(descr "LCSC parts (easyeda2kicad)"))\n'
                '  (lib (name "Device")(type "KiCad")(uri "${KICAD9_SYMBOL_DIR}/Device.kicad_sym")(options "")(descr ""))\n'
                '  (lib (name "power")(type "KiCad")(uri "${KICAD9_SYMBOL_DIR}/power.kicad_sym")(options "")(descr ""))\n' +
                "".join('  (lib (name "%s")(type "KiCad")(uri "${KICAD9_SYMBOL_DIR}/%s.kicad_sym")(options "")(descr ""))\n' % (m, m)
                        for m in more) + ')\n')
    with open(os.path.join(HERE, "fp-lib-table"), "w") as f:
        f.write('(fp_lib_table\n  (version 7)\n  (lib (name "lcsc")(type "KiCad")(uri "${KIPRJMOD}/../lib/lcsc.pretty")(options "")(descr "LCSC parts (easyeda2kicad)"))\n)\n')
    pro = os.path.join(HERE, NAME + ".kicad_pro")
    if not os.path.exists(pro):
        with open(pro, "w") as f:
            f.write('{\n  "meta": {"filename": "%s.kicad_pro", "version": 3},\n  "sheets": [["%s", "Root"]]\n}\n' % (NAME, ROOT))
    print("%s.kicad_sch: %d symbols, %.0f x %.0f mm" % (NAME, len(placed), W, H))


if __name__ == "__main__":
    main()
