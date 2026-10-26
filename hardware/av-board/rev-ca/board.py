"""Rev C-A's parts and nets: the Tang Mega 138K SOM on its own carrier (rev-c/design.md), HDMI from
an ADV7511 at up to 1080p60, as rev B's but fed 24-bit RGB 4:4:4 (the SOM has the pins rev B's
headers lacked).

    python3 rev-ca/board.py        # checks the design and prints a summary
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "rev-c"))
from carrier import *  # noqa: E402,F401,F403
import floor  # noqa: E402
from carrier import PARTS, unconnected, summary, common, clocks, som, common_groups, check, chip_pins  # noqa: E402
from circuits import TX, adv7511  # noqa: E402

NAME = "av-board-ca"
REV = "C-A"
VARIANTS = {"hand-jacks": ["J1", "J2", "J3", "J4", "J5", "J14"]}

common(second_rail="1V8B")
clocks(refclk=False)

# ---------------------------------------------------------------------------
# ADV7511 (rev B's circuit, rev-b/board.py and review.md; 24-bit input here)
# ---------------------------------------------------------------------------

# 24-bit RGB 4:4:4, input ID 0: R[7:0] on D35-D28, G[7:0] on D23-D16, B[7:0] on D11-D4; the other
# inputs to GND [HWG Table 5, 6.1.1]. Every pixel at full colour: 4:2:2's halved chroma is the
# console's limit, not the scaler's
u2 = adv7511({"D%d" % (top - 7 + i): "OUT_%s%d" % (c, i) for c, top in (("R", 35), ("G", 23), ("B", 11)) for i in range(8)})

# ---------------------------------------------------------------------------
# The SOM, the FPGA pins assigned last
# ---------------------------------------------------------------------------

# the ADV7511's FPGA lines -> its pad (the audio lines' through their 49.9 R)
ADV7511_PADS = {net: num for num, net in u2.items() if net.startswith("OUT_")}
ADV7511_PADS.update({"OUT_" + net[3:]: num for num, net in u2.items() if net.startswith("TX_") and net[3:] in
                     ("MCLK", "SCLK", "LRCLK", "I2S0", "SPDIF")})
tx_pins, tx_body = chip_pins("lcsc:LQFP-100_L14.0-W14.0-P0.50-LS16.0-BL", floor.ADV7511_AT, 0, ADV7511_PADS)
SOM_NETS = som(common_groups() + [("adv7511", tx_pins, {}, tx_body)], rev=REV)


if __name__ == "__main__":
    sys.exit(summary(check([lambda: unconnected("U2", TX, lambda name: name == "SPDIF_OUT")])))
