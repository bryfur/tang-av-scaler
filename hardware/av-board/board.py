"""The AV board's parts and nets: the one source the schematic and the PCB are generated from.

Each part has a reference, a value, its symbol and footprint, its LCSC number (JLCPCB assembly)
and a map pin -> net. The circuit and its sources are described in design.md; the comments here
only name the source of each value.

    python3 board.py        # checks the design and prints a summary
"""

import os
import re
import sys
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
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
# 2026-10-24 with tools in the README; "basic" parts where one exists).
TWO = {
    "R0402": ("Device:R", "Resistor_SMD:R_0402_1005Metric"),
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
    ("R0402", "316k"): "C25777", ("R0402", "390k"): "C2909352",
    ("C0402", "6.8p"): "C1576", ("C0402", "30p"): "C1570", ("C0402", "220p"): "C1530",
    ("C0402", "1n"): "C1523", ("C0402", "10n"): "C15195", ("C0402", "100n"): "C1525",
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
    lib = parse(open(os.path.join(HERE, "lib", "lcsc.kicad_sym")).read())
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

# Net on each header pin (design.md "The two headers"); the rest are grounds. The FPGA can take
# any bit on any pin, so each bus is in the order its lines leave the chip (seen from the header),
# which keeps them from crossing: J10 in the order of the 75 R arrays under the ADV7842 (only LLC,
# held to the clock-capable CLK pin, crosses Y6/Y7); J9 round the ADV7511 from its left side
# (audio, VSYNC) over its top (HSYNC .. C1) down its right (C2 .. SCL), then INT/PD from its
# bottom. The PCM1808's I2S is on J9's left end, next to it. gen_pcb.py counts the crossings.
J10_NET = {n: "IN_" + s for n, s in {
    1: "C0", 2: "C1", 3: "C2", 4: "C3", 5: "VS", 6: "HS", 7: "C4", 8: "C5", 9: "DE", 10: "C6",
    13: "C7", 14: "Y0", 15: "Y1", 16: "Y2", 17: "Y3", 18: "Y4", 19: "Y5", 20: "LLC", 21: "Y6", 22: "Y7",
    23: "SCL", 24: "INT1", 25: "SDA", 26: "RESET_N", 31: "KEY1", 32: "KEY2"}.items()}
J9_NET = {n: "OUT_" + s for n, s in {
    30: "LRCLK", 29: "SCLK", 28: "I2S0", 27: "MCLK", 26: "VSYNC", 25: "HSYNC", 24: "DE", 23: "Y0",
    22: "Y1", 21: "Y2", 20: "Y3", 19: "Y4", 18: "Y5", 17: "Y6", 16: "Y7", 15: "C0", 14: "CLK", 13: "C1",
    10: "C2", 9: "C3", 8: "C4", 7: "C5", 6: "C6", 5: "C7", 4: "SDA", 3: "SCL", 2: "INT", 1: "PD"}.items()}
J9_NET.update({39: "IN_DOUT", 40: "IN_BCK", 37: "IN_SCKI", 38: "IN_LRCK"})


def header(ref, nets, note):
    pins = {}
    for n in range(1, 41):
        pins[str(n)] = "+5V" if n == 11 else nets.get(n, "GND")
    return part(ref, "2x20 socket", "lcsc:2.54-2*20P", "lcsc:HDR-TH_40P-P2.54-V-F-R2-C20-S2.54-2", "C5124634",
                pins, note=note)


block("headers")
header("J10", J10_NET, "to the Console's J10 (FPGA bank 4)")
header("J9", J9_NET, "to the Console's J9 (FPGA bank 2)")
C("22u", "+5V")
C("22u", "+5V")
C("100n", "+5V")

# Two buttons for the scaler's menu (the board covers the Console's own S1/S2): to J10 pins 31/32,
# 10 k pull-ups. Wired across a diagonal (pins 1 and 4), which is open/closed whichever way the
# switch pairs its pins inside.
for k in (1, 2):
    part("SW%d" % k, "TS-1187A-B-A-B", "lcsc:TS-1187A-B-A-B", "lcsc:SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5",
         "C318884", {"1": "IN_KEY%d" % k, "4": "GND"})
    R("10k", "3V3", "IN_KEY%d" % k)

# ---------------------------------------------------------------------------
# Power (design.md "Power")
# ---------------------------------------------------------------------------

block("power")
# 3V3: TPS7A7001 from +5 V; R1 169 k, R2 30.1 k [TI Table 2]; 10 uF in and out [TI 6.3]
part("U5", "TPS7A7001DDAR", "lcsc:TPS7A7001DDAR", "lcsc:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL-EP", "C60719",
     {"3": "+5V", "2": "+5V", "6": "3V3", "7": "FB_3V3", "8": "GND", "9": "GND", "1": "GND", "4": "GND", "5": "GND"})
C("10u", "+5V", size="C0805")
C("10u", "3V3", size="C0805")
R("169k", "3V3", "FB_3V3")
R("30.1k", "FB_3V3", "GND")

# 2V5: TLV62569 buck [TI Fig. 5]: 4.7 uF in, 2.2 uH, 10 uF out, R1 316 k / R2 100 k (Eq. 2), 6.8 pF
part("U4", "TLV62569DBVR", "lcsc:TLV62569DBVR", "lcsc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR", "C141836",
     {"1": "+5V", "2": "GND", "3": "SW_2V5", "4": "+5V", "5": "FB_2V5"})
C("4.7u", "+5V")
two(nxt("L"), "L3015", "2.2uH", "SW_2V5", "2V5")
C("10u", "2V5", size="C0805")
R("316k", "2V5", "FB_2V5")
R("100k", "FB_2V5", "GND")
C("6.8p", "2V5", "FB_2V5")

# 1.8 V enable from 3V3 through 100 k, 470 nF [PSU Fig. 2; EBZ R100/C39]: 3.3 V first
R("100k", "3V3", "EN_1V8")
C("470n", "EN_1V8")

# 1V8A (ADV7842) and 1V8B (ADV7511): TPS7A7001 from 2V5, R1 78.7 k / R2 30.1 k [TI Table 2]
for u, out, fb, lc in (("U6", "1V8A", "FB_1V8A", "C60719"), ("U7", "1V8B", "FB_1V8B", "C60719")):
    part(u, "TPS7A7001DDAR", "lcsc:TPS7A7001DDAR", "lcsc:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL-EP", lc,
         {"3": "2V5", "2": "EN_1V8", "6": out, "7": fb, "8": "GND", "9": "GND", "1": "GND", "4": "GND", "5": "GND"})
    C("10u", "2V5", size="C0805")
    C("22u", out)
    R("78.7k", out, fb)
    R("30.1k", fb, "GND")

# ADV7842 rails: an NFE61PT472C1H9L per rail, 33 uF tantalum + 10 uF after it [EBZ sheet 10;
# UG-214 Fig. 178]
for fl, src, rail in (("FL1", "1V8A", "AV_VDD"), ("FL2", "1V8A", "AV_AVDD"), ("FL3", "1V8A", "AV_CVDD"),
                      ("FL4", "1V8A", "AV_PVDD"), ("FL5", "3V3", "AV_DVDDIO"), ("FL6", "3V3", "AV_TVDD")):
    part(fl, "NFE61PT472C1H9L", "lcsc:NFE61PT472C1H9L", "lcsc:FILTER-SMD_NFE61PT472C1H9L", "C79933",
         {"1": src, "2": "GND", "3": rail})
    CT(rail)
    C("10u", rail)

# ADV7511 rails: 10 uH + 10 uF per domain group [HWG Fig. 23, 7.1]
for rail in ("TX_DVDD", "TX_AVDD", "TX_PLVDD"):
    two(nxt("L"), "L4018", "10uH", "1V8B", rail)
    C("10u", rail)


# ---------------------------------------------------------------------------
# ADV7842 (design.md "ADV7842KBCZ-5")
# ---------------------------------------------------------------------------

block("adv7842")
AV = lib_pins("lcsc:ADV7842KBCZ-5")
u1 = {}
for name, nums in AV.items():
    net = {"GND": "GND", "TVDD": "AV_TVDD", "AVDD": "AV_AVDD", "CVDD": "AV_CVDD", "VDD": "AV_VDD",
           "PVDD": "AV_PVDD", "DVDDIO": "AV_DVDDIO", "VDD_SDRAM": "AV_DVDDIO"}.get(name)
    if net:
        for n in nums:
            u1[n] = net


def ball(name):
    (n,) = AV[name]
    return n


# Analog inputs: 24 R series, 51 R to GND, 0.1 uF to AINx [EBZ sheet 1; UG-214 App. B]
for jack, sig, ain, lc, colour in (("J1", "Y", "AIN4", "C4992678", "black"), ("J2", "PB", "AIN6", "C4992678", "black"),
                                   ("J3", "PR", "AIN5", "C4991691", "red")):
    part(jack, "RCA " + {"Y": "Y", "PB": "Pb", "PR": "Pr"}[sig],
         "lcsc:RCJ-011" if colour == "black" else "lcsc:RCJ-014", "lcsc:CONN-TH_RCJ-011", lc,
         {"2": "RCA_" + sig, "1": "GND"}, note=colour + " RCJ-01x")
    R("24", "RCA_" + sig, "TERM_" + sig)
    R("51", "TERM_" + sig, "GND")
    C("100n", "TERM_" + sig, "AIN_" + sig)
    u1[ball(ain)] = "AIN_" + sig
C("1n", "TERM_Y", "SYNC_Y")                    # sync on Y [EBZ C98]
u1[ball("SYNC2")] = "SYNC_Y"

# Crystal: 28.63636 MHz, 390 k across, 30 pF loads [UG-214 Fig. 170 formula for CL = 20 pF]
part("Y1", "28.63636MHz 20pF", "lcsc:SMD-5032_2P28.63636M20pF", "lcsc:CRYSTAL-SMD_L5.0-W3.2", "C362486",
     {"1": "XTALP", "2": "XTALN"})
R("390k", "XTALP", "XTALN")
C("30p", "XTALP")
C("30p", "XTALN")
u1[ball("XTALP")] = "XTALP"
u1[ball("XTALN")] = "XTALN"

# REFP/REFN: 0.1 uF each to GND, 10 uF between [EBZ C105, C2, C150]
u1[ball("REFP")] = "REFP"
u1[ball("REFN")] = "REFN"
C("100n", "REFP")
C("100n", "REFN")
C("10u", "REFP", "REFN")

R("499", "RTERM", "GND")                        # [UG-214 Fig. 177 R3]
u1[ball("RTERM")] = "RTERM"

# Pixel port: series resistors next to the ADV7842 [EBZ sheet 6: 75 R arrays]
# in ball-row order (B, C, D ... N), so each array serves four neighbouring balls
OUT_BALLS = [("P4", "C0"), ("P5", "C1"), ("P6", "C2"), ("P7", "C3"),
             ("VS/FIELD", "VS"), ("HS/CS", "HS"), ("P8", "C4"), ("P9", "C5"),
             ("FIELD/DE", "DE"), ("P10", "C6"), ("P11", "C7"), ("P16", "Y0"),
             ("P17", "Y1"), ("P18", "Y2"), ("P19", "Y3"), ("P20", "Y4"),
             ("P21", "Y5"), ("P22", "Y6"), ("P23", "Y7"), ("LLC", "LLC")]
for k in range(0, len(OUT_BALLS), 4):
    pins = {}
    for j, (pname, sig) in enumerate(OUT_BALLS[k:k + 4]):
        u1[ball(pname)] = "AV_" + sig
        pins[str(1 + j)] = "AV_" + sig
        pins[str(8 - j)] = "IN_" + sig
    part(nxt("RN"), "75", "lcsc:4D02WGJ0750TCE", "lcsc:RES-ARRAY-SMD_0402-8P-L2.0-W1.0-BL", "C39128", pins)

# Control [UG-214 App. C, Table 1; DS; EBZ]
u1[ball("SCL")] = "IN_SCL"
u1[ball("SDA")] = "IN_SDA"
R("4.7k", "3V3", "IN_SCL")
R("4.7k", "3V3", "IN_SDA")
u1[ball("~{RESET}")] = "IN_RESET_N"
R("4.7k", "IN_RESET_N", "GND", note="held in reset until the FPGA drives it")
u1[ball("INT1")] = "IN_INT1"
R("4.7k", "3V3", "IN_INT1")
u1[ball("~{PWRDN1}")] = "PWRDN1"
R("4.7k", "3V3", "PWRDN1")
u1[ball("TEST8")] = "TEST8"
R("4.7k", "3V3", "TEST8", note="UG-214: TEST8 to 3.3 V via 4.7 k")
R("4.7k", "TEST8", "GND", dnp=True, note="data sheet Rev B: TEST8 to GND via 4.7 k")
for t in ("TEST4", "TEST5", "SYNC3", "SYNC4", "TRI4", "SDRAM_VREF"):
    u1[ball(t)] = "GND"
for name in ("DDCB_SCL", "DDCA_SCL", "VGA_SCL", "TTX_SCL"):
    u1[ball(name)] = "PD_" + name
    R("10k", "PD_" + name, "GND")
for name in ("RXA_5V", "RXB_5V"):
    u1[ball(name)] = "+5V"
dq = ["SDRAM_DQ%d" % i for i in range(16)] + ["SDRAM_LDQS", "SDRAM_UDQS"]
for k in range(0, 16, 4):
    pins = {}
    for j, name in enumerate(dq[k:k + 4]):
        u1[ball(name)] = "PD_" + name
        pins[str(1 + j)] = "PD_" + name
        pins[str(8 - j)] = "GND"
    part(nxt("RN"), "4.7k", "lcsc:4D02WGJ0472TCE", "lcsc:RES-ARRAY-SMD_0402-8P-L2.0-W1.0-BL", "C29586", pins)
for name in dq[16:]:
    u1[ball(name)] = "PD_" + name
    R("4.7k", "PD_" + name, "GND")

part("U1", "ADV7842KBCZ-5", "lcsc:ADV7842KBCZ-5", "lcsc:CSPBGA-256_L17.0-W17.0-R16-C16-P1.00-BL", "C514382", u1)

# Decoupling, per rail exactly as UG-214 Fig. 179
for rail, n10n, n100n, n220p in (("AV_TVDD", 2, 2, 9), ("AV_AVDD", 5, 0, 9), ("AV_CVDD", 3, 1, 0),
                                 ("AV_VDD", 5, 0, 2), ("AV_DVDDIO", 6 + 4, 0, 8 + 5), ("AV_PVDD", 1, 1, 0)):
    for _ in range(n10n):
        C("10n", rail)
    for _ in range(n100n):
        C("100n", rail)
    for _ in range(n220p):
        C("220p", rail)

# ---------------------------------------------------------------------------
# PCM1808 [TI Fig. 26, 8.2.2]
# ---------------------------------------------------------------------------

block("pcm1808")
part("U3", "PCM1808PWR", "lcsc:PCM1808PWR", "lcsc:TSSOP-14_L5.0-W4.4-P0.65-LS6.4-BL", "C55513",
     {"1": "VREF", "2": "GND", "3": "5VA", "4": "3V3", "5": "GND", "6": "IN_SCKI", "7": "IN_LRCK", "8": "IN_BCK",
      "9": "IN_DOUT", "10": "MD0", "11": "MD1", "12": "FMT", "13": "AUD_VINL", "14": "AUD_VINR"})
for pin in ("MD0", "MD1", "FMT"):
    R("10k", pin, "GND")                         # slave mode, I2S [TI 8.2.2.1]
# VCC: ferrite from +5 V, at the PCM1808
two(nxt("FB"), "FB0603", "600R", "+5V", "5VA")
for rail in ("VREF", "5VA", "3V3"):
    C("100n", rail)
    C("10u", rail)
for jack, ch, lc, colour in (("J4", "L", "C4992678", "black"), ("J5", "R", "C4991691", "red")):
    part(jack, "RCA " + ch, "lcsc:RCJ-011" if colour == "black" else "lcsc:RCJ-014", "lcsc:CONN-TH_RCJ-011", lc,
         {"2": "RCA_" + ch, "1": "GND"}, note=colour + " RCJ-01x")
    R("10k", "RCA_" + ch, "AUD_DIV_" + ch)
    R("10k", "AUD_DIV_" + ch, "GND")
    C("1n", "AUD_DIV_" + ch)
    C("1u", "AUD_DIV_" + ch, "AUD_VIN" + ch)

# ---------------------------------------------------------------------------
# ADV7511 (design.md "ADV7511KSTZ")
# ---------------------------------------------------------------------------

block("adv7511")
TX = lib_pins("lcsc:ADV7511KSTZ")
u2 = {}
for name, nums in TX.items():
    net = {"GND": "GND", "DVDD": "TX_DVDD", "AVDD": "TX_AVDD", "PVDD": "TX_AVDD", "PLVDD": "TX_PLVDD",
           "BGVDD": "TX_PLVDD", "MVDD": "3V3"}.get(name)
    if net:
        for n in nums:
            u2[n] = net


def pin(name):
    (n,) = TX[name]
    return n


for i in range(8):
    u2[pin("D%d" % (8 + i))] = "OUT_Y%d" % i       # style 1, right-justified [HWG Table 7]
    u2[pin("D%d" % (16 + i))] = "OUT_C%d" % i
for i in list(range(0, 8)) + list(range(24, 36)):
    u2[pin("D%d" % i)] = "GND"                      # unused inputs to GND [HWG 6.1.1]
for name, net in (("CLK", "OUT_CLK"), ("HSYNC", "OUT_HSYNC"), ("VSYNC", "OUT_VSYNC"), ("DE", "OUT_DE"),
                  ("SCL", "OUT_SCL"), ("SDA", "OUT_SDA"), ("INT", "OUT_INT"), ("PD", "OUT_PD"),
                  ("R_EXT", "R_EXT"), ("HPD", "HDMI_HPD"), ("DDCSDA", "HDMI_SDA"), ("DDCSCL", "HDMI_SCL"),
                  ("TX2+", "TMDS_D2_P"), ("TX2-", "TMDS_D2_N"), ("TX1+", "TMDS_D1_P"), ("TX1-", "TMDS_D1_N"),
                  ("TX0+", "TMDS_D0_P"), ("TX0-", "TMDS_D0_N"), ("TXC+", "TMDS_CK_P"), ("TXC-", "TMDS_CK_N")):
    u2[pin(name)] = net
for name in ("I2S1", "I2S2", "I2S3", "SPDIF", "DSD0", "DSD1", "DSD2", "DSD3", "DSD4", "DSD5", "DSDCLK",
             "CEC", "CEC_CLK", "HEAC+", "HEAC-"):
    u2[pin(name)] = "GND"                           # [HWG 6.1.1, 6.2.1, 6.4.1]
# Audio: 51 R series at the source (the header side) [HWG 7.3]
for name, sig in (("MCLK", "MCLK"), ("SCLK", "SCLK"), ("LRCLK", "LRCLK"), ("I2S0", "I2S0")):
    u2[pin(name)] = "TX_" + sig
    R("51", "OUT_" + sig, "TX_" + sig)
part("U2", "ADV7511KSTZ", "lcsc:ADV7511KSTZ", "lcsc:LQFP-100_L14.0-W14.0-P0.50-LS16.0-BL", "C179459", u2)
R("887", "R_EXT", "GND")                            # 1 % [HWG 7.6]
R("2k", "3V3", "OUT_SCL")                           # [HWG 7.4]
R("2k", "3V3", "OUT_SDA")
R("2k", "3V3", "OUT_INT")                           # [HWG 6.3.4]
R("2k", "OUT_PD", "GND")                            # address 0x72, PD active high [HWG 6.1.5]
# 0.1 uF at every supply pin, adjacent pins sharing [HWG 7.1, Fig. 23]: DVDD 1, 19, 49, 76+77;
# AVDD 29, 34, 41; PVDD 24+25; PLVDD 21; BGVDD 26; MVDD 47
for rail, n in (("TX_DVDD", 4), ("TX_AVDD", 4), ("TX_PLVDD", 2), ("3V3", 1)):
    for _ in range(n):
        C("100n", rail)

# HDMI connector, type A [HWG Fig. 27, 6.3]
part("J6", "HDMI-001", "lcsc:HDMI-001", "lcsc:HDMI-SMD_19P-P0.50-H-F", "C138388",
     {"1": "TMDS_D2_P", "2": "GND", "3": "TMDS_D2_N", "4": "TMDS_D1_P", "5": "GND", "6": "TMDS_D1_N",
      "7": "TMDS_D0_P", "8": "GND", "9": "TMDS_D0_N", "10": "TMDS_CK_P", "11": "GND", "12": "TMDS_CK_N",
      "15": "HDMI_SCL", "16": "HDMI_SDA", "17": "GND", "18": "HDMI_5V", "19": "HDMI_HPD",
      "20": "GND", "21": "GND", "22": "GND", "23": "GND"})
# ESD on the TMDS lines: TI TPD4E05U06, 0.5 pF per line (HWG 6.3.2.1 asks for < 0.6 pF; its example,
# Panasonic EZAEG2A50AX, needs one part per line), flow-through: each line crosses pad n and the
# NC pad opposite it (10, 9, 7, 6)
for ref, (a, b_, c, d) in (("U9", ("TMDS_D2_P", "TMDS_D2_N", "TMDS_D1_P", "TMDS_D1_N")),
                           ("U10", ("TMDS_D0_P", "TMDS_D0_N", "TMDS_CK_P", "TMDS_CK_N"))):
    part(ref, "TPD4E05U06DQAR", "lcsc:TPD4E05U06DQAR_C138714", "lcsc:USON-10_L2.5-W1.0-P0.50-BL", "C138714",
         {"1": a, "10": a, "2": b_, "9": b_, "4": c, "7": c, "5": d, "6": d, "3": "GND", "8": "GND"})
part("U8", "TPD4E05U06DQAR", "lcsc:TPD4E05U06DQAR_C138714", "lcsc:USON-10_L2.5-W1.0-P0.50-BL", "C138714",
     {"1": "HDMI_SCL", "10": "HDMI_SCL", "2": "HDMI_SDA", "9": "HDMI_SDA", "4": "HDMI_HPD", "7": "HDMI_HPD",
      "5": "HDMI_5V", "6": "HDMI_5V", "3": "GND", "8": "GND"})
R("2k", "HDMI_5V", "HDMI_SCL")                      # [HWG 6.3.3: 1.5-2 k to the HDMI 5 V]
R("2k", "HDMI_5V", "HDMI_SDA")
R("100k", "HDMI_HPD", "GND", note="keeps HPD low with no cable (not in HWG Fig. 27)")
two(nxt("F"), "PTC0805", "0.2A", "+5V", "HDMI_5V")
C("100n", "HDMI_5V")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def nets():
    out = {}
    for p in PARTS:
        for n, net in p.pins.items():
            out.setdefault(net, []).append((p.ref, n))
    return out


def check():
    refs = [p.ref for p in PARTS]
    dup = {r for r in refs if refs.count(r) > 1}
    assert not dup, dup
    errors = []
    # every net has at least two pins (single-pin nets are typos)
    for net, pins in nets().items():
        if len(pins) < 2:
            errors.append("net %s has one pin: %s" % (net, pins))
    # ADV7842: every ball either connected or one that UG-214 App. C says to float
    floats = re.compile(r"^(P\d+|RX[AB]_.*|SYNC_OUT|HPA_[AB]|EP_.*|~\{EP_CS\}|CEC|DDC[AB]_SDA|VGA_SDA|"
                        r"HS_IN.*|VS_IN.*|TRI[123]|AIN\d+|SYNC1|AOUT|TTX_SDA|MCLK|AP\d|SCLK|INT2|TEST6|TEST7|"
                        r"AVLINK|(~\{)?SDRAM_(A\d+|BA\d|CS|RAS|CAS|WE|CK|CKE)\}?)$")
    u1p = [p for p in PARTS if p.ref == "U1"][0].pins
    for name, nums in AV.items():
        for n in nums:
            if n not in u1p and not floats.match(name):
                errors.append("U1 ball %s (%s) unconnected" % (n, name))
    u2p = [p for p in PARTS if p.ref == "U2"][0].pins
    for name, nums in TX.items():
        for n in nums:
            if n not in u2p and name not in ("SPDIF_OUT",):
                errors.append("U2 pin %s (%s) unconnected" % (n, name))
    return errors


if __name__ == "__main__":
    errs = check()
    for e in errs:
        print("ERROR", e)
    by = {}
    for p in PARTS:
        by.setdefault(p.block, []).append(p)
    print("%d parts, %d nets" % (len(PARTS), len(nets())))
    for b, ps in by.items():
        print("  %-8s %3d" % (b, len(ps)))
    sys.exit(1 if errs else 0)
