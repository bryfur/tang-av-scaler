#!/usr/bin/env python3
"""boardcheck.py [MODE ...] [table=N]: the board's picture against the model's, pixel for pixel, on what the
console sends now.  The picture is frozen (the link), the four newest fields read out of the DDR3
(fields.py), and for each deinterlacing mode asked for (default 0 8 4 12: motion adaptive,
motion compensated, along edges, both) the rows where that mode matters are read back from the
output (grab.py) and compared with sim/model.py's frame from the same fields and the board's own
settings.  A simulation that passes is not the hardware: this is (a synthesis fault in the edge
search was found this way, 2026-11-13).

The scaler's table is the one the board says it has (the design's own, or the learnt ones in
gateware/tables; another: TABLE=its file); table=N: the setting changed to N for the check (0 FSR's,
1 the learnt pair, ...: tools/table.py), and many more rows compared.

It needs something moving in the picture for the modes to differ from plain motion adaptive (it
says how many pixels do).  AV_HOST (default 192.168.1.112), AVB_TTY (default the link's console).
Leaves the picture running in the mode it found.  OUT (default /tmp/boardcheck): the fields
(fields.json), the board's and the model's rows (PNG)."""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../sim"))
HOST = os.environ.get("AV_HOST", "192.168.1.112")
os.environ.setdefault("AVB_TTY", "tcp:%s:2323" % HOST)
OUT = os.environ.get("OUT", "/tmp/boardcheck")

from PIL import Image, ImageChops

import avb
import grab
import model
import still


def api(**kw):
    url = "http://%s/api/video" % HOST
    data = urllib.parse.urlencode(kw).encode() if kw else None
    r = urllib.request.urlopen(url, data, timeout=10).read()
    return None if kw else json.loads(r)


def main():
    modes = [int(a) for a in sys.argv[1:] if a.isdigit()] or [0, 8, 4, 12]
    tabset = next((int(a[6:]) for a in sys.argv[1:] if a.startswith("table=")), None)
    os.makedirs(OUT, exist_ok=True)
    v = api()
    s, was = v["set"], v["set"]["mode"]
    tabwas = s.get("table", 0)
    if tabset is not None and tabset != tabwas:
        api(table=tabset)
        time.sleep(2.5)                 # (the link's status is a second old; the table takes 0.2 s)
        v = api()
    # the table the scaler has
    t = v.get("tab", {"slot": 0, "state": 0, "have": 1})
    for _ in range(16):                 # (the link's status is up to a second old)
        ask = v["set"].get("table", 0)
        ask = 0 if ask == 0 else 1 + (1 if v["set"]["aa"] else 0) if ask == 1 else ask + 1
        if t["state"] <= 0 and (t["slot"] == ask or not t["have"] >> ask & 1):
            break
        time.sleep(0.5)
        v = api()
        t = v["tab"]
    slot = max(t["slot"], 0)
    tabfile = os.environ.get("TABLE") or {0: None, 1: os.path.join(HERE, "../tables/learnt-plain.tab"),
                                         2: os.path.join(HERE, "../tables/learnt-aa12.tab")}.get(slot, "")
    if tabfile == "":
        sys.exit("boardcheck: the scaler has the table in slot %d (%s): TABLE=its file" % (slot, t["names"][slot]))
    tab = model.table_load(tabfile) if tabfile else None
    print("the scaler's table: slot %d (%s)%s" % (slot, t.get("names", ["FSR"])[slot], ", %d entries read back wrong" % t["bad"] if t.get("bad") else ""), flush=True)
    if v["in"] != "480i" or not v["hist"]:
        sys.exit("boardcheck: 480i with four fields in order is wanted (in %s, hist %s)" % (v["in"], v["hist"]))
    api(freeze=1, osd=0)
    time.sleep(0.5)
    try:
        # (the monitor's port is open only while it is read: the link does not pass settings on to the
        # scaler while a host has that port)
        m = avb.Mon()
        d = m.r(still.DSTAT)
        latest, pc = d >> 3 & 7, d >> 13 & 1
        fields = [still.field(m, (latest - k) & 7) for k in range(3, -1, -1)]
        pars = [(pc + k) & 1 for k in range(3, -1, -1)]
        m.close()
        json.dump({"pars": pars, "fields": fields}, open(os.path.join(OUT, "fields.json"), "w"))
        crop = tuple(v["shown"])
        first = max(0, crop[2] - 4) & ~1
        skip = (max(0, crop[2] - 24) & ~7)
        print("frozen: %d x %d from %d, %d shown; the fields read" % (crop[1], crop[3], crop[0], crop[2]), flush=True)

        def frame(mode):
            rows = model.frame_1080(fields, pars, mode & 3, s["thr"], s["aa_thr"] if s["aa"] else None, s["sharp"], bool(s["aa_dbg"]),
                                    bool(s["aa_diag"]), bool(s["aa_corner"]), crop, s["nr"], bool(s["dn"]), False, bool(mode & 4),
                                    None, bool(mode & 8) and mode & 3 == 0, first, skip, tab)
            im = Image.new("RGB", (1920, 1080))
            im.putdata([p for row in rows for p in row])
            return im
        plain = frame(0)
        bad = 0
        for mode in modes:
            want = plain if mode == 0 else frame(mode)
            box = ImageChops.difference(want, plain).getbbox()
            y0, y1 = (max(0, box[1] - 8), min(1080, box[3] + 8)) if box else (500, 580)
            if tabset is not None and mode == modes[0]:
                y0, y1 = 300, 780
            moved = sum(1 for p in ImageChops.difference(want, plain).getdata() if p != (0, 0, 0))
            api(mode=mode)
            time.sleep(1.5)
            m = avb.Mon()
            t_open = time.time()
            deint = m.r(0x35)
            if deint >> 7 & 1 != mode >> 2 & 1 or deint >> 3 & 1 != (mode >> 3 & 1 and mode & 3 == 0) or deint & 3 != mode & 3:
                sys.exit("boardcheck: mode %d was not taken (DEINT %08x)" % (mode, deint))
            got = Image.new("RGB", (1920, y1 - y0))
            rows, again = [], []
            for r in range(y0, y1, 2):                  # (the design takes two rows a frame)
                # (a read that loses bytes on the way is asked again: the picture is frozen)
                for go in range(4):
                    try:
                        rows += grab.rows8(m, r, 1, 1920)[:2]
                        break
                    except SystemExit as e:
                        again.append("row %d, %.1f s after the port was opened: %s" % (r, time.time() - t_open, e))
                        if go == 3:
                            raise
                        try:
                            m.close()
                        except Exception:
                            pass
                        time.sleep(0.5)
                        m = avb.Mon()
            m.close()
            for t in again:
                print("  asked again: " + t, flush=True)
            got.putdata([p for row in rows[:y1 - y0] for p in row])
            diff = ImageChops.difference(got, want.crop((0, y0, 1920, y1)))
            n = sum(1 for p in diff.getdata() if p != (0, 0, 0))
            bad += n
            got.save(os.path.join(OUT, "board_%d.png" % mode))
            want.crop((0, y0, 1920, y1)).save(os.path.join(OUT, "model_%d.png" % mode))
            print("mode %2d (DEINT %08x): rows %d to %d: %d pixels differ from the model%s  (the mode changes %d pixels of the frame)" % (
                mode, deint, y0, y1 - 1, n, "" if n else ": the same", moved), flush=True)
    finally:
        api(freeze=0, mode=was, osd=s["osd"], table=tabwas)
    print("PASS" if not bad else "FAIL")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
