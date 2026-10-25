"""Rev B's parts and nets: the one source its schematic and PCB are generated from.

Rev A with the ADV7842 (256-ball BGA) replaced by the ADV7181D (64-lead LFCSP): the same
16-bit 4:2:2 pixel bus to J10, the same audio and HDMI side. The circuit and its sources are in
design.md; the comments here only name the source of each value.

    python3 rev-b/board.py        # checks the design and prints a summary
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kit"))
from parts import *  # noqa: E402,F401,F403
from parts import PARTS, block, part, two, nxt, R, C, lib_pins, header, common_errors, unconnected, summary  # noqa: E402

NAME = "av-board-b"          # the KiCad project and fab files
REV = "B"
# Assembly variants (kit/gen_fab.py): the parts each leaves to be soldered by hand.
# hand-jacks: the five RCA jacks (through-hole: about $9 of parts a board, and JLCPCB's through-hole fee)
VARIANTS = {"hand-jacks": ["J1", "J2", "J3", "J4", "J5"]}


# Net on each header pin (design.md "The two headers"); the rest are grounds. The FPGA can take
# any bit on any pin, so each bus is in the order its lines leave the chip, seen from the header,
# which keeps them from crossing (gen_pcb.py counts the crossings). J10: the ADV7181D's lines
# round its left side, along its bottom and up its right, with LLC on the clock-capable CLK pin
# (20); J9 as rev A (the ADV7511 and PCM1808 sit where they did).
J10_NET = {n: "IN_" + s for n, s in {
    1: "RESET_N", 2: "SDA", 3: "SCL", 4: "Y7", 5: "Y6", 6: "Y5", 7: "Y4", 8: "DE", 9: "VS", 10: "INT",
    13: "HS", 14: "Y3", 15: "Y2", 16: "Y1", 17: "Y0", 18: "C7", 19: "C6", 20: "LLC", 21: "C5", 22: "C4",
    23: "C3", 24: "C2", 25: "C1", 26: "C0", 31: "KEY1", 32: "KEY2"}.items()}
J9_NET = {n: "OUT_" + s for n, s in {
    30: "LRCLK", 29: "SCLK", 28: "I2S0", 27: "MCLK", 26: "VSYNC", 25: "HSYNC", 24: "DE", 23: "Y0",
    22: "Y1", 21: "Y2", 20: "Y3", 19: "Y4", 18: "Y5", 17: "Y6", 16: "Y7", 15: "C0", 14: "CLK", 13: "C1",
    10: "C2", 9: "C3", 8: "C4", 7: "C5", 6: "C6", 5: "C7", 4: "SDA", 3: "SCL", 2: "INT", 1: "PD"}.items()}
J9_NET.update({39: "IN_DOUT", 40: "IN_BCK", 37: "IN_SCKI", 38: "IN_LRCK"})


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
# The supply tree (design.md "Power", review.md): +5 V -> TLV62569 buck -> 3V6 -> TPS7A7001 3V3 ->
# two TPS7A7001 1.8 V LDOs (1V8A: ADV7181D, 1V8B: ADV7511). Each LDO is enabled by its own input,
# so a 1.8 V rail rises behind 3V3 and can never pass it, and once in regulation trails it by
# 1.5 V: the ADV7181D's supply-to-supply limits (DVDDIO - PVDD and AVDD - DVDD within -0.3..+2 V
# [DS Table 5]) hold at power-up by construction. Rev A started 3V3 30 ms before the 1.8 V rails,
# a 3.3 V difference.

# 3V6: TLV62569 buck [TI Fig. 5, 8.2.2]: R2 100 k, R1 499 k: 0.6 V x (1 + 4.99) = 3.594 V (Eq. 2);
# 6.8 pF feed-forward for R2 = 100 k [TI 8.2.2.2]; 2.2 uH (Isat 2 A, 78 mR) with 10 uF out
# [Table 4]; 10 uF in (TI's 4.7 uF, doubled: the 0805's 5 V DC bias leaves about 60 %). About
# 0.6 A out
part("U4", "TLV62569DBVR", "lcsc:TLV62569DBVR", "lcsc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR", "C141836",
     {"1": "+5V", "2": "GND", "3": "SW_3V6", "4": "+5V", "5": "FB_3V6"})
C("10u", "+5V", size="C0805")
two(nxt("L"), "L3015", "2.2uH", "SW_3V6", "3V6")
C("10u", "3V6", size="C0805")
R("499k", "3V6", "FB_3V6")
R("100k", "FB_3V6", "GND")
C("6.8p", "3V6", "FB_3V6")

# 3V3: TPS7A7001 from 3V6, EN tied to IN [TI 7.3.1]; R1 169 k / R2 30.1 k = 3.307 V [TI Table 2];
# 10 uF in and out [TI 6.3]; 220 pF feed-forward across R1 [TI 8.1.2: more than 47 uF on the
# output, here about 60 uF with the 1.8 V LDOs' inputs]. 0.3 V headroom against about 0.1 V
# dropout at its 0.6 A [TI Fig. 3]; 0.18 W
part("U5", "TPS7A7001DDAR", "lcsc:TPS7A7001DDAR", "lcsc:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL-EP", "C60719",
     {"3": "3V6", "2": "3V6", "6": "3V3", "7": "FB_3V3", "8": "GND", "9": "GND", "1": "GND", "4": "GND", "5": "GND"})
C("10u", "3V6", size="C0805")
C("10u", "3V3", size="C0805")
R("169k", "3V3", "FB_3V3")
R("30.1k", "FB_3V3", "GND")
C("220p", "3V3", "FB_3V3")

# 1V8A (ADV7181D, about 0.13 A) and 1V8B (ADV7511, at most 0.18 A [HWG 6.8.2: 326 mW]): TPS7A7001
# from 3V3, EN tied to IN; R1 78.7 k / R2 30.1 k = 1.807 V [TI Table 2]; 10 uF in and out, 220 pF
# feed-forward as for 3V3. 0.2 and 0.27 W
for u, out, fb, lc in (("U6", "1V8A", "FB_1V8A", "C60719"), ("U7", "1V8B", "FB_1V8B", "C60719")):
    part(u, "TPS7A7001DDAR", "lcsc:TPS7A7001DDAR", "lcsc:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL-EP", lc,
         {"3": "3V3", "2": "3V3", "6": out, "7": fb, "8": "GND", "9": "GND", "1": "GND", "4": "GND", "5": "GND"})
    C("10u", "3V3", size="C0805")
    C("10u", out, size="C0805")
    R("78.7k", out, fb)
    R("30.1k", fb, "GND")
    C("220p", out, fb)

# Power-down: 3V3 carries the heavier load and may fall faster than 1V8A; a Schottky from 1V8A
# to 3V3 holds 1V8A within its forward drop (about 0.25 V at a few mA) of 3V3, inside the
# ADV7181D's -0.3 V [DS Table 5]. Reverse-biased (1.5 V) in operation
part("D1", "B5819W", "Device:D_Schottky", "Diode_SMD:D_SOD-123", "C8598", {"1": "3V3", "2": "1V8A"})

# ADV7181D rails: a ferrite per supply, 10 uF after it [PSU: a ferrite per rail, 10 uF bulk; DS
# Fig. 9 draws the rails filtered off-sheet]. BLM18PG121SN1D: 120 R at 100 MHz, 2 A, 50 mR: AVDD's
# 0.2 A drops 10 mV (the 0.2 A / 0.45 R bead first fitted dropped 90 mV and put AVDD under its
# 3.15 V minimum at the 3V3 LDO's low limit)
for src, rail in (("1V8A", "AV_DVDD"), ("1V8A", "AV_PVDD"), ("3V3", "AV_AVDD"), ("3V3", "AV_DVDDIO")):
    two(nxt("FB"), "FB0603", "120R", src, rail)
    C("10u", rail)

# ADV7511 rails: 10 uH + 10 uF per domain group [HWG Fig. 23, 7.1]
for rail in ("TX_DVDD", "TX_AVDD", "TX_PLVDD"):
    two(nxt("L"), "L4018", "10uH", "1V8B", rail)
    C("10u", rail)


# ---------------------------------------------------------------------------
# ADV7181D (design.md "ADV7181DBCPZ")
# ---------------------------------------------------------------------------

block("adv7181d")
AV = lib_pins("lcsc:ADV7181DBCPZ-RL")
u1 = {}
for name, nums in AV.items():
    net = {"GND": "GND", "EP": "GND", "DVDD": "AV_DVDD", "PVDD": "AV_PVDD", "AVDD": "AV_AVDD",
           "DVDDIO": "AV_DVDDIO"}.get(name)
    if net:
        for n in nums:
            u1[n] = net


def pin(name):
    (n,) = AV[name]
    return n


# Component in: 75 R to GND at the jack, 0.1 uF to the input; Y on AIN10, Pb on AIN8, Pr on AIN6
# [DS Fig. 9, Table 8 "Component YUV": Y = AIN10, U = AIN8, V = AIN6]; Y also through 1 nF to SOY,
# sync on Y [DS Fig. 9]
# Jacks: CUI RCJ-01x, one footprint, the last digit the colour (1 black, 2 red, 3 white, 4 yellow
# [RCJ-01 data sheet]): yellow RCJ-014 ($1.69, 200 in stock) where rev A had black RCJ-011 ($3.82,
# 40), red RCJ-012 for Pr and R; the silkscreen names each input
RCA_YELLOW, RCA_RED = "C4991844", "C4991691"
for jack, sig, ain, lc, colour in (("J1", "Y", "AIN10", RCA_YELLOW, "yellow"), ("J2", "PB", "AIN8", RCA_YELLOW, "yellow"),
                                   ("J3", "PR", "AIN6", RCA_RED, "red")):
    part(jack, "RCA " + {"Y": "Y", "PB": "Pb", "PR": "Pr"}[sig], "lcsc:RCJ-014", "lcsc:CONN-TH_RCJ-011", lc,
         {"2": "RCA_" + sig, "1": "GND"}, note=colour + " RCJ-01x")
    two(nxt("R"), "R0603", "75", "RCA_" + sig, "GND")
    C("100n", "RCA_" + sig, "AIN_" + sig)
    u1[pin(ain)] = "AIN_" + sig
C("1n", "RCA_Y", "SYNC_Y")
u1[pin("SOY")] = "SYNC_Y"
# ESD on the three video inputs (DS Fig. 9 has none; the jacks are where a charged cable lands):
# the TMDS lines' TPD4E05U06, 0.42-0.5 pF per line, 5.5 V stand-off [TI-ESD], flow-through, on the
# lines between the jacks and the terminations; its fourth channel unused (pads 5/6 open)
part("U11", "TPD4E05U06DQAR", "lcsc:TPD4E05U06DQAR_C138714", "lcsc:USON-10_L2.5-W1.0-P0.50-BL", "C138714",
     {"1": "RCA_Y", "10": "RCA_Y", "2": "RCA_PB", "9": "RCA_PB", "4": "RCA_PR", "7": "RCA_PR", "3": "GND", "8": "GND"})

# Crystal: 28.63636 MHz fundamental [DS Table 1, pin 21], 1 M across [DS Fig. 9]. YXC
# X50322863636MSB2GI: 20 pF load, +-10 ppm at 25 C, +-20 ppm over temperature, 40 R ESR, 5032
# two-pad (476 in stock; rev A's TXM part had 68). Load caps C = 2 (CL - Cstray) - Cpg = 31 pF
# [AN-1260], 33 pF C0G the nearest JLCPCB basic part: about 1 pF over the load, about -9 ppm;
# worst case -39 ppm against the decoder's +-50 ppm [DS Table 1]. Fig. 9's 47 pF suit its own
# crystal
part("Y1", "28.63636MHz 20pF", "lcsc:SMD-5032_2P28.63636M20pF", "lcsc:CRYSTAL-SMD_L5.0-W3.2", "C112564",
     {"1": "XTAL", "2": "XTAL1"})
R("1M", "XTAL", "XTAL1")
C("33p", "XTAL")
C("33p", "XTAL1")
u1[pin("XTAL")] = "XTAL"
u1[pin("XTAL1")] = "XTAL1"

# ADC references [DS Fig. 9]: CAPY2 to GND through 0.1 uF (twice); 10 uF + 0.1 uF + 10 nF from
# CAPY1 to CAPY2 and from CAPC2 to CAPY2; REFOUT and CML 10 uF + 0.1 uF each to GND
for name in ("CAPY1", "CAPY2", "CAPC2", "REFOUT", "CML"):
    u1[pin(name)] = name
C("100n", "CAPY2")
C("100n", "CAPY2")
for a in ("CAPY1", "CAPC2"):
    C("10u", a, "CAPY2")
    C("100n", a, "CAPY2")
    C("10n", a, "CAPY2")
for a in ("REFOUT", "CML"):
    C("10u", a)
    C("100n", a)

# PLL loop filter at ELPF: 1.69 k + 82 nF in series and 10 nF across, to PVDD [DS Fig. 8]
u1[pin("ELPF")] = "ELPF"
R("1.69k", "ELPF", "ELPF_RC")
C("82n", "ELPF_RC", "AV_PVDD")
C("10n", "ELPF", "AV_PVDD")

# Pixel port: 16-bit SDR 4:2:2, Y on P19-P12, CbCr on P9-P2 [DS Table 11, CP 16-bit SDR]; 33 R in
# series next to the chip on every output [DS Fig. 9]. Where four used pins sit side by side
# (P19-P16, P15-P12, P6-P4 + LLC) a 4 x 0402 array at the pins' own 0.5 mm pitch, in line with
# them (gen_pcb.py); a single 0402 on each of the others
OUT_ARRAYS = [[("P19", "Y7"), ("P18", "Y6"), ("P17", "Y5"), ("P16", "Y4")],
              [("P15", "Y3"), ("P14", "Y2"), ("P13", "Y1"), ("P12", "Y0")],
              [("P6", "C4"), ("P5", "C3"), ("P4", "C2"), ("LLC", "LLC")]]
OUT_SINGLE = [("P9", "C7"), ("P8", "C6"), ("P7", "C5"), ("P3", "C1"), ("P2", "C0"), ("HS/CS", "HS"),
              ("VS", "VS"), ("FIELD/DE", "DE")]
for group in OUT_ARRAYS:
    pins = {}
    for j, (pname, sig) in enumerate(group):
        u1[pin(pname)] = "AV_" + sig
        pins[str(1 + j)] = "AV_" + sig
        pins[str(8 - j)] = "IN_" + sig
    part(nxt("RN"), "33", "lcsc:4D02WGJ0750TCE", "lcsc:RES-ARRAY-SMD_0402-8P-L2.0-W1.0-BL", "C25501", pins)
for pname, sig in OUT_SINGLE:
    u1[pin(pname)] = "AV_" + sig
    R("33", "AV_" + sig, "IN_" + sig)

# Control [DS Fig. 9, Table 7]: I2C to the FPGA with 4.7 k pull-ups (rev A's), ALSB high (write
# address 0x42), PWRDWN high through 4.7 k, INT 4.7 k to DVDDIO (open drain by default)
u1[pin("SCLK")] = "IN_SCL"
u1[pin("SDATA")] = "IN_SDA"
R("4.7k", "3V3", "IN_SCL")
R("4.7k", "3V3", "IN_SDA")
u1[pin("#RESET")] = "IN_RESET_N"
R("4.7k", "IN_RESET_N", "GND", note="held in reset until the FPGA drives it (5 ms low minimum [DS pin 51])")
u1[pin("#INT")] = "IN_INT"
R("4.7k", "AV_DVDDIO", "IN_INT")
u1[pin("ALSB")] = "ALSB"
R("4.7k", "AV_DVDDIO", "ALSB")
u1[pin("#PWRDWN")] = "PWRDWN"
R("4.7k", "AV_DVDDIO", "PWRDWN")
# Unused inputs held low: fast blank (SCART only), the 5-wire sync inputs (graphics only)
for name in ("FB", "HS_IN/CS_IN", "VS_IN"):
    u1[pin(name)] = "PD_" + re.sub(r"\W", "_", name)
    R("10k", "PD_" + re.sub(r"\W", "_", name), "GND")

part("U1", "ADV7181DBCPZ-RL", "lcsc:ADV7181DBCPZ-RL", "lcsc:LFCSP-64_L9.0-W9.0-P0.50-BL-EP7.1", "C514378", u1)

# Decoupling, per supply pin as DS Fig. 9: DVDDIO and DVDD 2 x (0.1 uF + 10 nF), PVDD and AVDD
# 0.1 uF + 10 nF
for rail, n in (("AV_DVDDIO", 2), ("AV_DVDD", 2), ("AV_PVDD", 1), ("AV_AVDD", 1)):
    for _ in range(n):
        C("100n", rail)
        C("10n", rail)

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
two(nxt("FB"), "FB0603", "120R", "+5V", "5VA")
for rail in ("VREF", "5VA", "3V3"):
    C("100n", rail)
    C("10u", rail)
for jack, ch, lc, colour in (("J4", "L", RCA_YELLOW, "yellow"), ("J5", "R", RCA_RED, "red")):
    part(jack, "RCA " + ch, "lcsc:RCJ-014", "lcsc:CONN-TH_RCJ-011", lc,
         {"2": "RCA_" + ch, "1": "GND"}, note=colour + " RCJ-01x")
    R("10k", "RCA_" + ch, "AUD_DIV_" + ch)
    R("10k", "AUD_DIV_" + ch, "GND")
    C("220p", "AUD_DIV_" + ch)                   # anti-alias RC: 5 k x 220 pF, 145 kHz [TI 10.1.3]
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
# Audio: series resistors at the source (the header side) [HWG 7.3: 51 R]; 49.9 R, the nearest
# JLCPCB basic part
for name, sig in (("MCLK", "MCLK"), ("SCLK", "SCLK"), ("LRCLK", "LRCLK"), ("I2S0", "I2S0")):
    u2[pin(name)] = "TX_" + sig
    R("49.9", "OUT_" + sig, "TX_" + sig)
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
R("10k", "HDMI_HPD", "GND", note="0 V on HPD with no sink [HWG 6.1.4: 10 k +-10 %]")
two(nxt("F"), "PTC0805", "0.2A", "+5V", "HDMI_5V")
C("100n", "HDMI_5V")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check():
    errors = common_errors()
    # ADV7181D: every pin connected but the unused inputs and outputs [DS Table 7]
    floats = re.compile(r"^(AIN[1-5]|AIN7|AIN9|SOG|SFL/SYNC_OUT|P0|P1|P10|P11)$")
    errors += unconnected("U1", AV, floats.match)
    errors += unconnected("U2", TX, lambda name: name == "SPDIF_OUT")
    return errors


if __name__ == "__main__":
    sys.exit(summary(check()))
