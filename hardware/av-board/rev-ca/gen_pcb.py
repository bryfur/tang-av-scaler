#!/usr/bin/env python3
"""Rev C-A's PCB: rev C's carrier (rev-c/layout.py) with the ADV7511 beside the SOM's J21 (as rev
C-B's retimer): its data side faces J21 across a 7 mm gap, its TMDS lines leave its right side and
run up the right edge to the ESD arrays and the receptacle on the back edge (kit/tmds_layout.py,
rev B's lines).

    python3 rev-ca/gen_pcb.py [--route]       (see kit/pcbkit.py)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "rev-c"))
import board  # noqa: E402
import floor  # noqa: E402
from layout import RevC  # noqa: E402


class RevCA(RevC):
    POWER_NETS = RevC.POWER_NETS | {"1V8B", "TX_DVDD", "TX_AVDD", "TX_PLVDD"}
    CLOCK_NETS = RevC.CLOCK_NETS | {"OUT_CLK"}
    BIAS_NETS = RevC.BIAS_NETS | {"R_EXT", "FB_1V8B"}
    BUSES = [("J22", "U1"), ("J21", "U2")]
    # rev B's TMDS pairs and the pins between them (rev-b/gen_pcb.py, kit/tmds_layout.py)
    TMDS = [("D2", "43", "42", "U9", "1", "10", "2", "9", "1", "3"),
            ("D1", "40", "39", "U9", "4", "7", "5", "6", "4", "6"),
            ("D0", "36", "35", "U10", "1", "10", "2", "9", "7", "9"),
            ("CK", "33", "32", "U10", "4", "7", "5", "6", "10", "12")]
    TMDS_INWARD = {"34": 1.7, "37": 1.7, "38": 2.4, "41": 1.7}
    # 1.27 mm between the pairs up their 55 mm run (5 W at 0.25 mm: TI SPRAAR7 3.1), as rev C-B's;
    # the keep-outs along their first leg too, the 15-17 mm from the ADV7511 to the corner (past its
    # break-out). That leg keeps the chip's pitch: spread there, the outer pairs would cross the
    # HPD and OUT_INT pins' lines beside them (pins 30 and 45, out of the chip alongside CK and D2)
    TMDS_SPREAD = 0.52
    TMDS_KEEP_OUT = True

    TX_CHIP = (floor.ADV7511_AT, 8.0)

    def hand(self):
        h = RevC.hand(self)
        h["U2"] = floor.ADV7511_AT + (0, "F")      # (rev B: -90, turned 90)
        x, y = floor.ADV7511_AT
        h["U7"] = (x + 11.5, y + 13.0, 0, "F")     # 1V8B, by the ADV7511's supply pins
        return h

    def tx_fanout(self, b, fps):
        self.tmds_fanout(b, fps)

    def fanout_skip(self):
        return RevC.fanout_skip(self) | {"U2.37"}


LAYOUT = RevCA(board, HERE)

if __name__ == "__main__":
    LAYOUT.cli(sys.argv)
