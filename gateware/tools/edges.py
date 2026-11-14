#!/usr/bin/env python3
"""edges.py [N] [OUT.json]: the anti-aliasing's edges as the design keeps them from frame to frame
(rtl/smaa_hist.v: the setting aa_keep, 1 or more), read from the board's memory N times (default 4),
the picture running: how many there are, and how many pixels' edges are other than the read
before's.  On a picture that stands still that is the shimmer the keeping is there to stop (a read
takes a second or two, so each is of several frames: a count of what changed in that time, not
frame by frame).  OUT.json: the reads kept.  AV_HOST, AVB_TTY as boardcheck.py."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("AV_HOST", "avscaler.local")
os.environ.setdefault("AVB_TTY", "tcp:%s:2323" % HOST)
import avb
import still


def main():
    n = int(next((a for a in sys.argv[1:] if a.isdigit()), 4))
    outf = next((a for a in sys.argv[1:] if a.endswith(".json")), None)
    reads = []
    for k in range(n):
        m = avb.Mon()
        t = time.time()
        e = still.edges(m)
        m.close()
        reads.append(e)
        total = sum(a + b for row in e for a, b in row)
        line = "read %d (%.1f s): %d edges" % (k, time.time() - t, total)
        if k:
            line += ", %d pixels' other than the read before's" % sum(a != b for ra, rb in zip(reads[k - 1], e) for a, b in zip(ra, rb))
        print(line, flush=True)
        time.sleep(0.5)
    if outf:
        json.dump(reads, open(outf, "w"))


if __name__ == "__main__":
    main()
