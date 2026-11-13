#!/usr/bin/env python3
"""fields.py OUT.json [N]: the newest N fields (default 4) out of the DDR3, as the capture put them
there, for the models (sim/model.py deinterlace() takes them as they are): freeze the picture
first (the link: freeze=1), or they change while they are read.  OUT.json: {"pars": [...],
"fields": [[[cb, y0, cr, y1] x 360] x 240] x N}, the oldest first; pars: each field's F as the
deinterlacer counts it (the newest's from DSTAT, the others in turn).  Through the monitor
(AVB_TTY): about a minute a field."""
import json
import sys
import time

import avb
import still


def main():
    out = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    m = avb.Mon()
    d = m.r(still.DSTAT)
    latest, pc = d >> 3 & 7, d >> 13 & 1
    fields, t = [], time.time()
    for k in range(n - 1, -1, -1):
        fields.append(still.field(m, (latest - k) & 7))
        print("slot %d read (%.0f s)" % ((latest - k) & 7, time.time() - t), flush=True)
    # (pc: the newest field is the bottom one (deint.v: its lines the frame's odd ones); F = pc with top_f 0)
    pars = [(pc + k) & 1 for k in range(n - 1, -1, -1)]
    json.dump({"pars": pars, "fields": fields, "dstat": d}, open(out, "w"))
    print("%s: %d fields, the newest in slot %d, F %s" % (out, n, latest, pars))


if __name__ == "__main__":
    main()
