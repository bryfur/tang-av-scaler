"""Rev C's floor plan, shared by both carriers (C-A: ADV7511, C-B: SN65DP159) and by both their
board.py (the FPGA pin assignment follows the geometry) and gen_pcb.py (placement).

A 130 x 100 mm board. The back edge (top) carries every cable: the six RCA jacks facing out (Y, Pb,
Pr, L, R, S/PDIF coax), the USB-C power input between the video and audio jacks (straight above
the SOM's 5 V pins, between the two analog front ends rather than through them) and the HDMI
receptacle at the right. The SOM sits below, turned 270 degrees from its place on the Console so
that

    J22 (banks 4, 5, 10, the 5 V input)  faces left:  the ADV7181D, PCM1808 and S/PDIF, under the jacks
    J21 (banks 2, 3, the transceivers)   faces right: the ADV7511 (C-A) or SN65DP159 (C-B) beside it
    J20 (JTAG, RECONFIG_N, DONE, READY)  faces front: the XIAO, buttons, LEDs, JTAG header

Either HDMI transmitter sits right beside J21, level with its upper end: its bus (C-A: 24-bit RGB at
up to 148.5 MHz) or lanes (C-B: up to 5.94 Gb/s) cross a few millimetres, and nothing digital
passes the audio block above; its TMDS lines run right, then up the right edge to the receptacle.

Coordinates in mm, KiCad's frame (y down), the board's top-left corner at (100, 50).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import som  # noqa: E402

X0, Y0, X1, Y1 = 100.0, 50.0, 230.0, 150.0
SOM_AT = (155.0, 110.0)             # the centre of the SOM's four holes
SOM_ANGLE = 270                     # from its place on the Console
JACK_Y = Y0 + 11.0                  # an RCA footprint's origin, its mouth 0.2 mm past the edge
# the back edge, left to right: x of each jack's (and the USB-C's) centre, 13 mm apart
BACK = {"J1": 109.0, "J2": 122.0, "J3": 135.0, "J15": 147.5, "J4": 160.0, "J5": 173.0, "J14": 186.0}
# the HDMI receptacle's block: rev B's (its TMDS ESD arrays, the receptacle) turned 90 degrees, on
# the back edge at the right: placed relative to HDMI_AT, where rev B's ADV7511 would sit (the
# receptacle 15 mm right of it). Rev C-B's 15.5 mm further left, 1 mm past the S/PDIF jack: its
# retimer's outputs then run about 66 mm to the receptacle, inside the 2 to 3 inches its driver is
# made for [TI-DP159 10.2.2]; rev C-A's ADV7511, whose right side its lines leave, sits too far right
HDMI_AT = (201.5, 70.8)
HDMI_AT_CB = (186.0, 70.8)
# rev C-A's ADV7511 (LQFP-100) at 0 degrees: its pixel inputs on its top and left sides (pins 51-100),
# their corner level with the top of J21's I/O pins (y 114-126: the transceivers' pins above them are
# unused here), so the left side's lines cross straight over and the top side's wrap round the
# corner, clear of the clock generator above; its TMDS pins (32-43) on its right side at y - 2.5 ..
# y + 3
ADV7511_AT = (188.5, 120.0)
# rev C-B's SN65DP159 (VQFN-48), turned 270: its inputs (pins 1-12) down its left side facing the
# transceivers' TX pins on J21 across a 7 mm gap (the AC capacitors between), centred on them;
# its outputs (25-36) down its right side, the TMDS lines from there to the receptacle
DP159_AT, DP159_ANGLE = (181.47, 108.85), 270
# the ADV7181D under the video jacks, analog side up (rev B's rotation); the XIAO at the front left,
# USB-C to the front edge (its module 17.8 x 21 mm, clear of the SOM)
U1_AT = (121.0, 90.0)
XIAO_AT = (112.0, 139.0)
VGA_AT = (104.5, 100.0)             # the VGA header, upright, left of the ADV7181D
PCM1808_AT = (166.5, 76.0)          # under the audio jacks
SPDIF_AT = (186.0, 76.0)            # the S/PDIF slicer, under its jack
CLOCK_AT = (178.0, 98.0)            # the clock generator, by J21's top (C-B: the transceivers' REFCLK0)
UI_AT = (186.0, 145.0)              # the buttons along the front edge


def rotate(x, y, angle):
    """KiCad's rotation (y down, positive angles counterclockwise on screen)."""
    a = math.radians(angle)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def connector(ref):
    """(x, y, angle) of a SOM receptacle on the board."""
    _, _, (dx, dy), angle = som.CONNECTORS[ref]
    ox, oy = rotate(dx, dy, SOM_ANGLE)
    return SOM_AT[0] + ox, SOM_AT[1] + oy, (angle + SOM_ANGLE) % 360


def pin_xy(ref, pin):
    """Where SOM receptacle ref's pin sits on the board."""
    count = som.CONNECTORS[ref][1]
    cx, cy, angle = connector(ref)
    px, py = rotate(*som.pad_xy(pin, count), angle)
    return cx + px, cy + py


def holes():
    return [(SOM_AT[0] + x, SOM_AT[1] + y) for x, y in (rotate(hx, hy, SOM_ANGLE) for hx, hy in som.HOLES)]
