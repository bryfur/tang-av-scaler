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
VARIANTS = {"hand-jacks": ["J1", "J2", "J3", "J4", "J5", "J14"]}

common(second_rail=None)
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
C("10u", "+5V", size="C0805")
two(nxt("L"), "L3015", "2.2uH", "SW_1V1", "1V1")
C("10u", "1V1", size="C0805")
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
# its five pins, 0.01 uF twice
C("10u", "3V3")
for _ in range(2):
    C("100n", "3V3")
C("10n", "3V3")
C("10u", "1V1")
for _ in range(5):
    C("100n", "1V1")
for _ in range(2):
    C("10n", "1V1")

# CEC from the FPGA (rev C-A's ADV7511 has its own engine): one open-drain FPGA pin through a 2N7002
# in the bidirectional level-shifter arrangement, gate at 3.3 V: either side pulls the other low.
# With the board off the gate is at 0 V and the body diode reversed: the TV's bus sees only the
# FET's leakage (nA at 3.3 V), as CEC requires of a powered-off device. 10 k up on the FPGA side
part(nxt("Q"), "2N7002", "lcsc:2N7002", "lcsc:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR", "C8545",
     {"1": "3V3", "2": "CEC_FPGA", "3": "HDMI_CEC"})
R("10k", "3V3", "CEC_FPGA")

# ---------------------------------------------------------------------------
# The SOM, the FPGA pins assigned last
# ---------------------------------------------------------------------------

# the SN65DP159's FPGA lines -> its pad; CEC's at the retimer too (its FET sits by the receptacle)
DP159_PADS = {net: num for num, net in u2.items() if net in ("DP_SCL", "DP_SDA", "DDC_SCL", "DDC_SDA", "DP_HPD", "DP_OE")}
DP159_PADS["CEC_FPGA"] = pin("HPD_SNK")
dp_pins, dp_body = chip_pins("lcsc:VQFN-48_L7.0-W7.0-P0.50-BL-EP4.1", floor.DP159_AT, floor.DP159_ANGLE, DP159_PADS)
SOM_NETS = som(common_groups() + [("dp159", dp_pins, {}, dp_body)], transceiver_lanes=LANES, rev=REV)


def _unused_dp_pins(name):
    # pins left open on purpose: strap pins set over I2C, the DisplayPort AUX pair, CEC_EN (for
    # dongles), NC
    return name in ("PRE_SEL", "SLEW_CTL", "TX_TERM_CTL", "SWAP/POL", "~{HDMI_SEL}/A1", "AUX_SRCn", "AUX_SRCp",
                    "CEC_EN", "NC")


if __name__ == "__main__":
    sys.exit(summary(check([lambda: unconnected("U2", DP, _unused_dp_pins)])))
