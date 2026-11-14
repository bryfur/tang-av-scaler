#!/usr/bin/env python3
"""table.py: the scaler's tables (rtl/easu.v's weights: gateware/tables/README.md).

  table.py make IN OUT.tab         a table file from IN: IN.json ({"py,px,ang,len": [12 weights]}), the four
                                   files IN0.hex to IN3.hex, or another .tab
  table.py hex IN OUT              ... as OUT0.hex to OUT3.hex (what the design is built with)
  table.py fsr OUT.tab             FSR's own (sim/fsr.py): what the design holds without any of this
  table.py list                    the board's tables: the slots, which the scaler has
  table.py send IN [SLOT] [NAME]   a table to the board (slot 3 to 7, default 3): the link keeps it in
                                   its flash and gives it to the FPGA's CPU
  table.py drop SLOT               the slot emptied
  table.py use N                   the setting: 0 FSR's, 1 the learnt pair (by the anti-aliasing), 2 on:
                                   slot 3 on

The board: AVX_HOST (the link's address; default 192.168.1.112).  Python's own library only."""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../sim"))
HOST = os.environ.get("AVX_HOST", "192.168.1.112")


def load(path):
    import model
    tab = model.table_load(path)
    keys = [(py, px, ang, li) for py in range(4) for px in range(8) for ang in range(32) for li in range(8)]
    for k in keys:
        q = tab.get(k)
        if q is None or len(q) != 12:
            raise SystemExit("%s: the entry %s: twelve weights wanted" % (path, k))
        if any(v < -512 or v > 511 for v in q):
            raise SystemExit("%s: the entry %s: a weight outside -512..511" % (path, k))
    odd = sum(1 for k in keys if sum(tab[k]) != 256)
    if odd:
        print("%s: %d entries' weights do not sum to 256 (the picture's brightness changes there)" % (path, odd))
    return tab


def to_bytes(tab):
    import model
    return b"".join(w.to_bytes(4, "little") for w in model.table_words(tab))


def video():
    return json.load(urllib.request.urlopen("http://%s/api/video" % HOST, timeout=5))


def show():
    v = video()
    t = v.get("tab")
    if not t or t["state"] < 0:
        print("the board's design has no port for tables (or its memory is not there)")
        return v
    states = ["", ", one on its way in", ", being read back", ", the design's own being kept"]
    for s, name in enumerate(t["names"]):
        if name or t["have"] >> s & 1:
            print("slot %d  %-22s %s%s" % (s, name or "?", "in the CPU's memory" if t["have"] >> s & 1 else "not in the CPU's memory yet",
                                           "; THE SCALER HAS IT" if s == t["slot"] else ""))
    print("the setting: table %d; the last one took %d ms to put in, %d entries read back wrong%s" % (
        v["set"]["table"], t["ms"], t["bad"], states[t["state"]] if 0 <= t["state"] < 4 else ""))
    return v


def main():
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    if a[0] == "make":
        open(a[2], "wb").write(to_bytes(load(a[1])))
    elif a[0] == "hex":
        import model
        w = model.table_words(load(a[1]))
        for k in range(4):
            open("%s%d.hex" % (a[2], k), "w").write("".join("%08x\n" % w[4 * n + k] for n in range(8192)))
    elif a[0] == "fsr":
        import fsr
        open(a[1], "wb").write(to_bytes(fsr.table()))
    elif a[0] == "list":
        show()
    elif a[0] == "send":
        slot = int(a[2]) if len(a) > 2 else 3
        name = a[3] if len(a) > 3 else os.path.splitext(os.path.basename(a[1]))[0]
        name = "".join(c if c.isascii() and (c.isalnum() or c in "._-") else "_" for c in name)[:23]     # (what the link keeps of it)
        d = to_bytes(load(a[1]))
        rq = urllib.request.Request("http://%s/api/table?slot=%d&name=%s" % (HOST, slot, name), data=d,
                                    headers={"Content-Type": "application/octet-stream"})
        print(urllib.request.urlopen(rq, timeout=60).read().decode().strip())
        # (the link gives it to the CPU in its next second or two)
        for _ in range(20):
            time.sleep(1)
            t = video().get("tab", {})
            if t.get("have", 0) >> slot & 1 and t.get("state") == 0:
                break
        show()
    elif a[0] == "drop":
        rq = urllib.request.Request("http://%s/api/table?slot=%d&drop=1" % (HOST, int(a[1])), data=b"")
        print(urllib.request.urlopen(rq, timeout=20).read().decode().strip())
    elif a[0] == "use":
        rq = urllib.request.Request("http://%s/api/video" % HOST, data=("table=%d" % int(a[1])).encode())
        urllib.request.urlopen(rq, timeout=10).read()
        time.sleep(2)                   # (the link's status is a second old)
        for _ in range(10):
            time.sleep(0.5)
            t = video().get("tab", {})
            if t.get("state") == 0:
                break
        show()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
