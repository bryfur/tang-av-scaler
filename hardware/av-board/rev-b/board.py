"""Rev B's parts and nets: the one source its schematic and PCB are generated from.

Rev A with the ADV7842 (256-ball BGA) replaced by the ADV7181D (64-lead LFCSP): the same
16-bit 4:2:2 pixel bus to J10, the same audio and HDMI side. The circuit and its sources are in
design.md; the comments here only name the source of each value.

    python3 rev-b/board.py        # checks the design and prints a summary
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kit"))
from parts import *  # noqa: E402,F401,F403
from parts import PARTS, block, part, two, nxt, R, C, lib_pins, header, common_errors, unconnected, summary  # noqa: E402
from circuits import (AV, TX, ADV7181D_OPEN, supply_tree, adv7181d, pcm1808, spdif, adv7511,  # noqa: E402
                      hdmi_receptacle, xiao, buttons_led)

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
    23: "C3", 24: "C2", 25: "C1", 26: "C0", 31: "KEY1", 32: "KEY2", 33: "LED"}.items()}
J10_NET.update({27: "SPDIF_RX", 28: "OUT_SPDIF", 35: "SPDIF_ORX", 36: "VGA_SDA_F", 34: "VGA_SCL_F"})
# J10 pins 29 and 30, the Console's SDRAM1_EXIO0/1, stay open: FPGA pins through its 0 R R29/R31, but
# its schematic has places for 0 R to 3.3 V and GND instead (R30/R32, not fitted: MiSTer's SDRAM
# modules take their supply there), and a Console fitted so would put 3.3 V on U15's output. J9's
# pins 29/30 (the same on SDRAM0) carry OUT_SCLK/OUT_LRCLK, inputs here (49.9 R into the ADV7511):
# harmless either way
J10_NC = (29, 30)
J9_NET = {n: "OUT_" + s for n, s in {
    30: "LRCLK", 29: "SCLK", 28: "I2S0", 27: "MCLK", 26: "VSYNC", 25: "HSYNC", 24: "DE", 23: "Y0",
    22: "Y1", 21: "Y2", 20: "Y3", 19: "Y4", 18: "Y5", 17: "Y6", 16: "Y7", 15: "C0", 14: "CLK", 13: "C1",
    10: "C2", 9: "C3", 8: "C4", 7: "C5", 6: "C6", 5: "C7", 4: "SDA", 3: "SCL", 2: "INT", 1: "PD"}.items()}
J9_NET.update({39: "IN_DOUT", 40: "IN_BCK", 37: "IN_SCKI", 38: "IN_LRCK", 31: "OUT_CECCLK",
               32: "ESP_CS", 33: "ESP_IRQ", 34: "ESP_SCK", 35: "ESP_MISO", 36: "ESP_MOSI"})


block("headers")
header("J10", J10_NET, "to the Console's J10 (FPGA bank 4)", nc=J10_NC)
header("J9", J9_NET, "to the Console's J9 (FPGA bank 2)")
C("22u", "+5V", at="J9.11")                     # (at the headers' 5 V pins, where it comes in)
C("22u", "+5V", at="J10.11")
C("100n", "+5V", at="J9.11")

# The scaler's two menu buttons (the board covers the Console's own S1/S2) on J10 pins 31/32, its
# status LED on J10 pin 33 (kit/circuits.py)
block("control")
buttons_led()
# A Seeed XIAO (ESP32-C3/S3/C6) for Wi-Fi/Bluetooth (settings, a web page, firmware updates,
# controllers), USB-C towards the board's right edge: SPI to the FPGA (the XIAO the master: D4 chip
# select, D8 SCK, D9 MISO, D10 MOSI) and an interrupt from it (D5, active low), on J9's spare pins
# 32-36, through level translators that isolate either side when the other is off (kit/circuits.py
# xiao()). (The Console's own USB carries the FPGA's UART: the XIAO needs none.) With a chip select
# the FPGA leaves MISO undriven between transfers, so an ESP32-C3's strapping pin D9 (GPIO9) reads
# high at its reset
xiao({"D4": ("ESP_CS", "out"), "D5": ("ESP_IRQ", "in"), "D8": ("ESP_SCK", "out"), "D9": ("ESP_MISO", "in"),
      "D10": ("ESP_MOSI", "out")})

# ---------------------------------------------------------------------------
# The shared circuits (kit/circuits.py; design.md, review.md): the supplies, the ADV7181D front end
# with the SCART sync and VGA inputs, the PCM1808, the S/PDIF input, the ADV7511, the HDMI receptacle
# ---------------------------------------------------------------------------

block("power")
supply_tree("1V8B")
adv7181d()
pcm1808()
spdif("header")
# the ADV7511 fed 16-bit YCbCr 4:2:2, style 1, right-justified: Y on D15-D8, CbCr on D23-D16 [HWG
# Table 7]; SPDIF from the FPGA on J10 pin 28 (J9 is full); CEC_CLK on J9 pin 31
adv7511({**{"D%d" % (8 + i): "OUT_Y%d" % i for i in range(8)}, **{"D%d" % (16 + i): "OUT_C%d" % i for i in range(8)}})
hdmi_receptacle()


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check():
    errors = common_errors()
    # ADV7181D: every pin connected but the unused inputs and outputs [DS Table 7]
    errors += unconnected("U1", AV, ADV7181D_OPEN.match)
    errors += unconnected("U2", TX, lambda name: name == "SPDIF_OUT")
    return errors


if __name__ == "__main__":
    sys.exit(summary(check()))
