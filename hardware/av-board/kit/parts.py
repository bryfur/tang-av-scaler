"""What every revision's board.py is written with: the part record, the two-pin parts and their
LCSC numbers, the shared symbol/footprint library, and the Console's two headers.

A revision's board.py does `from parts import *`, then lists its parts with part(), R(), C() ...;
PARTS is the list gen_sch.py, gen_pcb.py and gen_fab.py read.
"""

import os
import sys
from dataclasses import dataclass, field

KIT = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(KIT), "lib")         # lib/lcsc.kicad_sym, lib/lcsc.pretty: all revisions'
sys.path.insert(0, KIT)
from sexp import parse, find, findall  # noqa: E402


@dataclass
class Part:
    ref: str
    value: str
    symbol: str             # lib:name
    footprint: str          # lib:name
    lcsc: str               # "" for parts not assembled (none so far)
    pins: dict = field(default_factory=dict)
    dnp: bool = False
    block: str = ""
    note: str = ""


PARTS = []
_block = [""]


def block(name):
    _block[0] = name


def part(ref, value, symbol, footprint, lcsc, pins, dnp=False, note=""):
    p = Part(ref, value, symbol, footprint, lcsc, dict(pins), dnp, _block[0], note)
    PARTS.append(p)
    return p


# Two-pin parts: kind -> (symbol, footprint).  Values -> LCSC numbers (JLCPCB stock, checked
# 2026-10-24/25 with tools in the README; "basic" parts where one exists).
TWO = {
    "R0402": ("Device:R", "Resistor_SMD:R_0402_1005Metric"),
    "R0603": ("Device:R", "Resistor_SMD:R_0603_1608Metric"),
    "C0402": ("Device:C", "Capacitor_SMD:C_0402_1005Metric"),
    "C0603": ("Device:C", "Capacitor_SMD:C_0603_1608Metric"),
    "C0805": ("Device:C", "Capacitor_SMD:C_0805_2012Metric"),
    "FB0603": ("Device:FerriteBead", "Inductor_SMD:L_0603_1608Metric"),
    "TANT_B": ("lcsc:TAJB336K010RNJ", "lcsc:CAP-SMD_L3.5-W2.8-R-RD"),
    "L4018": ("lcsc:NRS4018T100MDGJ", "lcsc:IND-SMD_L4.0-W4.0_SMNR4012"),
    "L3015": ("lcsc:FNR3015S2R2MT", "lcsc:IND-SMD_L3.0-W3.0_FNR30XXS"),
    "PTC0805": ("lcsc:BSMD0805-020-30V", "lcsc:F0805"),
}
LCSC = {
    ("R0402", "0"): "C17168", ("R0402", "24"): "C2909340", ("R0402", "51"): "C25125",
    ("R0402", "499"): "C4125", ("R0402", "887"): "C55968414", ("R0402", "2k"): "C4109",
    ("R0402", "4.7k"): "C25900", ("R0402", "10k"): "C25744", ("R0402", "30.1k"): "C29402",
    ("R0402", "78.7k"): "C67239", ("R0402", "100k"): "C25741", ("R0402", "169k"): "C25758",
    ("R0402", "316k"): "C25777", ("R0402", "390k"): "C2909352", ("R0402", "33"): "C25105",
    ("R0402", "1M"): "C26083", ("R0402", "1.69k"): "C25870", ("R0603", "75"): "C4275",
    ("R0402", "49.9"): "C25120", ("C0402", "33p"): "C1562", ("R0402", "499k"): "C25793",
    ("FB0603", "120R"): "C14709",
    ("C0402", "6.8p"): "C1576", ("C0402", "30p"): "C1570", ("C0402", "220p"): "C1530",
    ("C0402", "1n"): "C1523", ("C0402", "10n"): "C15195", ("C0402", "82n"): "C277511",
    ("C0402", "100n"): "C1525",
    ("C0603", "470n"): "C1623", ("C0603", "1u"): "C15849", ("C0603", "10u"): "C19702",
    ("C0805", "4.7u"): "C1779", ("C0805", "10u"): "C15850", ("C0805", "22u"): "C45783",
    ("FB0603", "600R"): "C1002", ("TANT_B", "33u"): "C7202", ("L4018", "10uH"): "C222882",
    ("L3015", "2.2uH"): "C167747", ("PTC0805", "0.2A"): "C883105",
}
POLAR = {"TANT_B"}           # pin 1 is + (the band side of the footprint)


def two(ref, kind, value, a, b, dnp=False, note=""):
    sym, fp = TWO[kind]
    return part(ref, value, sym, fp, LCSC[(kind, value)], {"1": a, "2": b}, dnp, note)


_n = {}


def nxt(prefix):
    _n[prefix] = _n.get(prefix, 0) + 1
    return "%s%d" % (prefix, _n[prefix])


def R(value, a, b, **kw):
    return two(nxt("R"), "R0402", value, a, b, **kw)


def C(value, a, b="GND", size=None, **kw):
    size = size or {"470n": "C0603", "1u": "C0603", "10u": "C0603", "4.7u": "C0805", "22u": "C0805"}.get(value, "C0402")
    return two(nxt("C"), size, value, a, b, **kw)


def CT(a, b="GND"):
    return two(nxt("C"), "TANT_B", "33u", a, b)


def lib_pins(symbol):
    """name -> [numbers] of a symbol in lib/lcsc.kicad_sym."""
    lib = parse(open(os.path.join(LIB, "lcsc.kicad_sym")).read())
    name = symbol.split(":")[1]
    sym = [s for s in findall(lib, "symbol") if s[1] == name][0]
    out = {}

    def walk(x):
        for e in x:
            if isinstance(e, list) and e and e[0] == "pin":
                out.setdefault(str(find(e, "name")[1]), []).append(str(find(e, "number")[1]))
            elif isinstance(e, list):
                walk(e)
    walk(sym)
    return out


# ---------------------------------------------------------------------------
# Headers: two 2x20 sockets on the bottom, onto the Console's J9 and J10.
# Pin -> the Console's signal name (Sipeed schematic, sheet FPGA_EXT_CONN).
# ---------------------------------------------------------------------------

HDR_NAMES = {1: "D0", 2: "D1", 3: "D2", 4: "D3", 5: "D4", 6: "D5", 7: "D6", 8: "D7", 9: "D15", 10: "D14",
             11: "+5V", 12: "GND", 13: "D13", 14: "D12", 15: "D11", 16: "D10", 17: "D9", 18: "D8",
             19: "A12", 20: "CLK", 21: "A9", 22: "A11", 23: "A7", 24: "A8", 25: "A5", 26: "A6", 27: "WE",
             28: "A4", 29: "EXIO0", 30: "EXIO1", 31: "CAS", 32: "RAS", 33: "CS", 34: "BA0", 35: "BA1",
             36: "A10", 37: "A0", 38: "A1", 39: "A2", 40: "A3"}
J9_BALL = {"D0": "E14", "D1": "E13", "D2": "C15", "D3": "C14", "D4": "B13", "D5": "C13", "D6": "A14", "D7": "A13",
           "D8": "B21", "D9": "A21", "D10": "B20", "D11": "A20", "D12": "A15", "D13": "A16", "D14": "B15",
           "D15": "B16", "A0": "D19", "A1": "E19", "A2": "C19", "A3": "C18", "A4": "E16", "A5": "D15", "A6": "D14",
           "A7": "A19", "A8": "A18", "A9": "C17", "A10": "D20", "A11": "D17", "A12": "B18", "BA0": "F15",
           "BA1": "C20", "CLK": "B17", "EXIO0": "F14", "EXIO1": "F13", "CAS": "E17", "CS": "F21", "RAS": "F16",
           "WE": "D16"}
J10_BALL = {"D0": "R19", "D1": "P19", "D2": "U21", "D3": "T21", "D4": "R17", "D5": "P16", "D6": "T18", "D7": "R18",
            "D8": "N13", "D9": "N14", "D10": "N17", "D11": "P17", "D12": "W21", "D13": "W22", "D14": "V17",
            "D15": "W17", "A0": "R16", "A1": "P15", "A2": "R14", "A3": "P14", "A4": "AA19", "A5": "AA21",
            "A6": "AA20", "A7": "AB22", "A8": "AB21", "A9": "Y22", "A10": "U17", "A11": "Y21", "A12": "V20",
            "BA0": "N15", "BA1": "U18", "CLK": "U20", "EXIO0": "AA18", "EXIO1": "AB18", "CAS": "Y19", "CS": "T20",
            "RAS": "Y18", "WE": "AB20"}


def header(ref, nets, note):
    """A 2x20 socket for the Console's J9 or J10: nets {pin: net}, +5 V on pin 11, the rest GND."""
    pins = {}
    for n in range(1, 41):
        pins[str(n)] = "+5V" if n == 11 else nets.get(n, "GND")
    return part(ref, "2x20 socket", "lcsc:2.54-2*20P", "lcsc:HDR-TH_40P-P2.54-V-F-R2-C20-S2.54-2", "C5124634",
                pins, note=note)


def nets():
    out = {}
    for p in PARTS:
        for n, net in p.pins.items():
            out.setdefault(net, []).append((p.ref, n))
    return out


def common_errors():
    """Duplicate references, and nets with one pin (typos)."""
    refs = [p.ref for p in PARTS]
    dup = {r for r in refs if refs.count(r) > 1}
    assert not dup, dup
    return ["net %s has one pin: %s" % (net, pins) for net, pins in nets().items() if len(pins) < 2]


def unconnected(ref, pinmap, ok):
    """Pins of a part (pinmap: name -> [numbers]) with no net whose name ok() does not accept."""
    have = [p for p in PARTS if p.ref == ref][0].pins
    return ["%s pin %s (%s) unconnected" % (ref, n, name)
            for name, nums in pinmap.items() for n in nums if n not in have and not ok(name)]


def summary(errs):
    """board.py's report: the errors, then the parts per block; the exit code."""
    for e in errs:
        print("ERROR", e)
    by = {}
    for p in PARTS:
        by.setdefault(p.block, []).append(p)
    print("%d parts, %d nets" % (len(PARTS), len(nets())))
    for b, ps in by.items():
        print("  %-8s %3d" % (b, len(ps)))
    return 1 if errs else 0
