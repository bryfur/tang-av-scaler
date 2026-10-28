"""Rev C-B's parts and nets: the Tang Mega 138K SOM on its own carrier (rev-c/design.md), HDMI 2.0
from the FPGA's transceivers through a TI SN65DP159 retimer, up to 4K60 (5.94 Gb/s a lane). The
FPGA does what the ADV7511 does in rev C-A (TMDS coding, HDMI 2.0 scrambling, audio data
islands, InfoFrames, CEC); the SN65DP159 turns the transceivers' AC-coupled CML into TMDS.

    python3 rev-cb/board.py        # checks the design and prints a summary

Sources: [TI-DP159] SN65DP159 data sheet SLLSEJ2G (refs/sn65dp159.pdf); [TI-BUCK] TLV62569.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "rev-c"))
from carrier import *  # noqa: E402,F401,F403
import floor  # noqa: E402
from carrier import PARTS, block, part, two, nxt, R, C, lib_pins, unconnected, summary, common, clocks, som, common_groups, check, chip_pins  # noqa: E402

NAME = "av-board-cb"
REV = "C-B"
VARIANTS = {"hand-jacks": ["J1", "J2", "J3", "J4", "J5"]}

# S/PDIF on rev B's 5-pin header (coax on a pigtail to an orange RCA, an optical module on pins 3-5)
# instead of C-A's orange jack: the receptacle takes the jack's place by the audio jacks and the
# board is 30 mm narrower (rev-c/floor.py)
common(second_rail=None, spdif_connectors="header")
clocks(refclk=True)

# ---------------------------------------------------------------------------
# SN65DP159 (RGZ, VQFN-48) [TI-DP159 Fig. 33, 10.2, 12]
# ---------------------------------------------------------------------------

block("dp159")
# 1V1 (VDD, 1.00-1.27 V [7.3], about 0.25 A at 6 Gb/s of its 435 mW): a TLV62569 buck from +5 V
# (an LDO from 3V3 would burn 0.5 W). R1 82.5 k / R2 100 k: 0.6 V x 1.825 = 1.095 V [TI-BUCK Eq. 2];
# 6.8 pF feed-forward for R2 = 100 k [8.2.2.2]; 2.2 uH with 10 uF for 0.6-1.2 V out [Table 4]
part("U7", "TLV62569DBVR", "lcsc:TLV62569DBVR", "lcsc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR", "C141836",
     {"1": "+5V", "2": "GND", "3": "SW_1V1", "4": "+5V", "5": "FB_1V1"})
# (each by its pin [TI-BUCK 10.1]: VIN's capacitor, the inductor at SW and the capacitor at its
# output, then the feedback divider by FB, away from the switch node. In rev B's 3V6 buck's order,
# the divider before the inductor, the divider's 6.8 pF took the inductor's place beside SW here:
# the inductor went above the chip, its SW pad turned away, 10.7 mm of SW track 0.2 mm from FB's)
C("10u", "+5V", size="C0805", at="U7.4")
L_1V1 = nxt("L")
two(L_1V1, "L3015", "2.2uH", "SW_1V1", "1V1")
C("10u", "1V1", size="C0805", at=L_1V1 + ".2")
R("82.5k", "1V1", "FB_1V1")
R("100k", "FB_1V1", "GND")
C("6.8p", "1V1", "FB_1V1")

DP = lib_pins("lcsc:SN65DP159RGZR")
u2 = {}
for name, nums in DP.items():
    net = {"GND": "GND", "EP": "GND", "VCC": "3V3", "VDD": "1V1"}.get(name)
    if net:
        for n in nums:
            u2[n] = net


def pin(name):
    (n,) = DP[name]
    return n


# Main link in: the transceivers' TX lanes through 100 nF each [7.3: 75-200 nF, 100 nF recommended].
# Which lane carries which TMDS channel is the gateware's choice; they are wired in the order they
# leave the SOM's J21 (top to bottom: lanes 0, 3, 2, 1) to the inputs' order down the retimer's
# side (D2, D1, D0, CLK), so the pairs do not cross
LANES = {0: "SER_D2", 3: "SER_D1", 2: "SER_D0", 1: "SER_CK"}
for ch in ("D2", "D1", "D0", "CK"):
    for pol, p in (("P", "p"), ("N", "n")):
        C("100n", "SER_%s_%s" % (ch, pol), "DP_%s_%s" % (ch, pol))
        u2[pin("IN_%s%s" % ({"CK": "CLK"}.get(ch, ch), p))] = "DP_%s_%s" % (ch, pol)
# Main link out: TMDS to the receptacle through the ESD arrays (rev-c/carrier.py hdmi_connector)
for ch in ("D2", "D1", "D0", "CK"):
    for pol, p in (("P", "p"), ("N", "n")):
        u2[pin("OUT_%s%s" % ({"CK": "CLK"}.get(ch, ch), p))] = "TMDS_%s_%s" % (ch, pol)
# Hot plug: the receptacle's HPD in (10 k down already), out to the FPGA [Pin Functions]
u2[pin("HPD_SNK")] = "HDMI_HPD"
u2[pin("HPD_SRC")] = "DP_HPD"
# DDC: the receptacle side (2 k to HDMI 5 V already) and the FPGA's side, 2 k to 3.3 V [Fig. 33];
# the retimer snoops it (TMDS_CLOCK_RATIO for HDMI 2.0 rates) and passes it through
u2[pin("SDA_SNK")] = "HDMI_SDA"
u2[pin("SCL_SNK")] = "HDMI_SCL"
u2[pin("SDA_SRC")] = "DDC_SDA"
u2[pin("SCL_SRC")] = "DDC_SCL"
R("2k", "3V3", "DDC_SDA")
R("2k", "3V3", "DDC_SCL")
# Control by I2C from the FPGA (HDMI 2.0 tuning needs it [10.3.1]): I2C_EN/PIN high; A0 low (10 k
# down), A1 low (its internal pull-down); 4.7 k pull-ups on the bus. PRE_SEL, SLEW_CTL,
# TX_TERM_CTL and SWAP/POL open (I2C sets them). OE from the FPGA with 100 nF to GND (it must rise
# after the supplies [10.2.1]; its internal 150-250 k pull-up and the 100 nF also make a power-on
# delay should the FPGA leave it floating)
u2[pin("I2C_EN/PIN")] = "DP_I2C_EN"
R("10k", "3V3", "DP_I2C_EN")
u2[pin("EQ_SEL/A0")] = "DP_A0"
R("10k", "DP_A0", "GND")
u2[pin("SCL_CTL")] = "DP_SCL"
u2[pin("SDA_CTL")] = "DP_SDA"
R("4.7k", "3V3", "DP_SCL")
R("4.7k", "3V3", "DP_SDA")
u2[pin("OE")] = "DP_OE"
C("100n", "DP_OE")
# Vsadj: 7.06 k 0.5 % for the RGZ package's HDMI 2.0 and 1.4b swing [10.3.1]
u2[pin("VSADJ")] = "DP_VSADJ"
R("7.06k", "DP_VSADJ", "GND")
part("U2", "SN65DP159RGZR", "lcsc:SN65DP159RGZR", "lcsc:VQFN-48_L7.0-W7.0-P0.50-BL-EP4.1", "C179676", u2)
# Decoupling [Fig. 33]: VCC 10 uF + 0.1 uF + 0.01 uF (two pins); VDD 10 uF and 0.1 uF at each of
# its five pins, 0.01 uF twice; each at its pin [12.2, Fig. 36: "as close to VCC and VDD pins as
# possible"]: VCC 13 and 43, VDD 14, 23, 24 on one side, 37 and 48 on the other
C("10u", "3V3", at="U2.13")
for n in ("13", "43"):
    C("100n", "3V3", at="U2." + n)
C("10n", "3V3", at="U2.43")
C("10u", "1V1", at="U2.24")
for n in ("14", "23", "24", "37", "48"):
    C("100n", "1V1", at="U2." + n)
for n in ("14", "37"):
    C("10n", "1V1", at="U2." + n)

# CEC from the FPGA (rev C-A's ADV7511 has its own engine): one open-drain FPGA pin through a 2N7002
# in the bidirectional level-shifter arrangement, gate at 3.3 V: either side pulls the other low.
# With the board off the gate is at 0 V and the body diode reversed: the TV's bus sees only the
# FET's leakage (nA at 3.3 V), as CEC requires of a powered-off device. 10 k up on the FPGA side
part(nxt("Q"), "2N7002", "lcsc:2N7002", "lcsc:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR", "C8545",
     {"1": "3V3", "2": "CEC_FPGA", "3": "HDMI_CEC"})
R("10k", "3V3", "CEC_FPGA")

# ---------------------------------------------------------------------------
# Test access: the SOM hides the FPGA's pins (rev B's sit on the Console's headers)
# ---------------------------------------------------------------------------

block("debug")
# J17, a 2 x 8 header (J8's part), left of the SOM: the three configuration buses (the ADV7181D's,
# the DP159's, the clock generator's), six spare FPGA pins for whatever the gateware brings out,
# a 3.3 V reference and ground. Each of its signal pins through 220 R at the header (Digilent's
# Pmod ports: 200 R): a probe slipping onto 3.3 V or ground, or a wire in the wrong place, drives
# at most 15 mA into a pin (an I2C tap shorted holds its bus, nothing driving it is hurt; a listener
# or an outside master works through it: 0.15 V at the 4.7 k pull-ups). The 3.3 V pin, beside
# ground, is a reference (a logic analyzer's threshold, a level shifter), not a supply: shorted,
# 50 mW in its resistor (62.5 mW rated) and the rail untouched
DEBUG = ["DBG%d" % k for k in range(6)]
J17_TAPS = {"1": "3V3", "3": "IN_SCL", "4": "IN_SDA", "5": "DP_SCL", "6": "DP_SDA", "7": "PLL_SCL",
            "8": "PLL_SDA", "9": "DBG0", "10": "DBG1", "11": "DBG2", "12": "DBG3", "13": "DBG4", "14": "DBG5"}


def _j(net):
    # the header's side of a pin's resistor
    return "DBG_VREF" if net == "3V3" else net + "_J"


part("J17", "DEBUG", "lcsc:Header-Male-2.54_2x8", "lcsc:HDR-TH_16P-P2.54-V-M-R2-C8-S2.54", "C68234",
     dict({"2": "GND", "15": "GND", "16": "GND"}, **{num: _j(net) for num, net in J17_TAPS.items()}),
     note="debug header")
for _num, _net in J17_TAPS.items():
    R("220", _net, _j(_net), at="J17." + _num, note="debug header pin protection")


def _by(net, other):
    # REF.PAD of the part joining net and other, its pin on net (a buck's inductor, the input fuse)
    p = [p for p in PARTS if set(p.pins.values()) == {net, other}][0]
    return p.ref + "." + [n for n, v in p.pins.items() if v == net][0]


# A bare test pad (not fitted, not assembled) on each rail by its regulator's output, two for ground;
# separate pads, not a header: a probe slipping on a header would short 5 V onto the 1.1 V core.
# TEST_PADS: ref -> its silkscreen label
TEST_PADS = {}
for net, at, label in (("+5V", _by("+5V", "VBUS_IN"), "+5V"), ("3V6", _by("3V6", "SW_3V6"), "3V6"),
                       ("3V3", "U5.6", "3V3"), ("1V8A", "U6.6", "1V8"), ("1V1", _by("1V1", "SW_1V1"), "1V1"),
                       ("3V0", "U24.5", "3V0"), ("2V5", "U18.5", "2V5"), ("5VA", "U12.5", "5VA")):
    ref = nxt("TP")
    part(ref, net, "Connector:TestPoint", "TestPoint:TestPoint_Pad_D1.5mm", "", {"1": net}, at=at,
         note="test pad")
    TEST_PADS[ref] = label
for at in ("U4.2", "U6.1"):
    ref = nxt("TP")
    part(ref, "GND", "Connector:TestPoint", "TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm", "", {"1": "GND"},
         at=at, note="ground test pad")
    TEST_PADS[ref] = "G"

# ---------------------------------------------------------------------------
# The SOM, the FPGA pins assigned last
# ---------------------------------------------------------------------------

# the SN65DP159's FPGA lines -> its pad; CEC's at the retimer too (its FET sits by the receptacle)
DP159_PADS = {net: num for num, net in u2.items() if net in ("DP_SCL", "DP_SDA", "DDC_SCL", "DDC_SDA", "DP_HPD", "DP_OE")}
DP159_PADS["CEC_FPGA"] = pin("HPD_SNK")
dp_pins, dp_body = chip_pins("lcsc:VQFN-48_L7.0-W7.0-P0.50-BL-EP4.1", floor.DP159_AT, floor.DP159_ANGLE, DP159_PADS)
SOM_NETS = som(common_groups(spdif_at=floor.SPDIF_AT_CB, ui_at=floor.UI_AT_CB) + [("dp159", dp_pins, {}, dp_body),
               ("debug", point(DEBUG, floor.DEBUG_AT_CB), {})], transceiver_lanes=LANES, rev=REV)


def _unused_dp_pins(name):
    # pins left open on purpose: strap pins set over I2C, the DisplayPort AUX pair, CEC_EN (for
    # dongles), NC
    return name in ("PRE_SEL", "SLEW_CTL", "TX_TERM_CTL", "SWAP/POL", "~{HDMI_SEL}/A1", "AUX_SRCn", "AUX_SRCp",
                    "CEC_EN", "NC")


if __name__ == "__main__":
    sys.exit(summary(check([lambda: unconnected("U2", DP, _unused_dp_pins)])))
