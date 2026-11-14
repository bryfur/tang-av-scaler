#!/usr/bin/env python3
"""net.py: the scaler's network (rtl/cnn.v; docs/cnn-upscaler.md) on the board.

  net.py status              is it there, is it on, rows it was late for
  net.py on | off            the setting (the link's: the web page's "Upscaler")
  net.py load MODEL.json     another network of the same shape (3 x 3: 1 -> 8 -> 8 -> 4): its weights, biases
                             and shifts (sim/model.py net_words()) given to the board, which puts them
                             into the network and keeps them in its own flash: they are there at every
                             start from then on (the design's own, sim/cnn/t8s.json, are what a board
                             that keeps none has).  Check with NET=MODEL.json tools/boardcheck.py
  net.py try MODEL.json      the same, not kept: until the board starts again
  net.py drop                the kept ones forgotten, the design's own put back
  net.py poke MODEL.json     put in through the monitor's port, past the board's CPU (a design or a
                             program from before 2026-11-14; not kept)

The board: AVX_HOST (default avscaler.local); the monitor as tools/avb.py finds it (AVB_TTY)."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../sim"))
HOST = os.environ.get("AVX_HOST", "avscaler.local")
os.environ.setdefault("AVB_TTY", "tcp:%s:2323" % HOST)
NET, NETA, NETD, NETS = 0x44, 0x45, 0x46, 0x47


def video():
    return json.load(urllib.request.urlopen("http://%s/api/video" % HOST, timeout=5))


def main():
    a = sys.argv[1:]
    if not a or a[0] == "status":
        v = video()
        n = v.get("net", {})
        print("the network: %s; the setting: %s; rows it was late for: %d; its weights: %s" % (
            "in this design" if n.get("there") else "NOT in this design", "on" if v["set"].get("net") else "off", n.get("under", 0),
            {0: "the design's own", 1: "put in since the start, not kept", 2: "\"%s\", kept in the board" % n.get("name")}.get(n.get("state"), "the design's own")))
    elif a[0] in ("on", "off"):
        urllib.request.urlopen("http://%s/api/video" % HOST, ("net=%d" % (a[0] == "on")).encode(), timeout=10).read()
        time.sleep(2)
        main_status = video()
        print("the setting: %s" % ("on" if main_status["set"].get("net") else "off"))
    elif a[0] in ("load", "try", "drop"):
        import struct
        import model
        import urllib.parse
        f = a[1] if a[0] != "drop" else os.path.join(HERE, "../sim/cnn/t8s.json")
        words = model.net_words(model.net_load(f))
        body = b"".join(struct.pack("<HI", addr, val) for addr, val in words)
        name = os.path.basename(f).rsplit(".", 1)[0][:23]
        if a[0] == "drop":
            print(urllib.request.urlopen("http://%s/api/net?drop=1" % HOST, b"", timeout=20).read().decode().strip())
        q = urllib.parse.urlencode({"name": name, "keep": 1 if a[0] == "load" else 0})
        t = time.time()
        try:
            r = urllib.request.urlopen(urllib.request.Request("http://%s/api/net?%s" % (HOST, q), body), timeout=30).read().decode().strip()
        except urllib.error.HTTPError as e:
            sys.exit("net.py: %s" % e.read().decode().strip())
        print("%d values: %s (%.1f s)" % (len(words), r, time.time() - t))
        if a[0] == "load":                      # (kept a step a time: a second or so)
            for _ in range(40):
                time.sleep(0.5)
                v = video()
                if v.get("net", {}).get("state") == 2 and not v.get("store", {}).get("busy"):
                    print("kept in the board's flash as \"%s\"" % v["net"].get("name"))
                    break
            else:
                sys.exit("net.py: not kept: %s" % json.dumps(v.get("store")))
    elif a[0] == "poke":
        import avb
        import model
        words = model.net_words(model.net_load(a[1]))
        m = avb.Mon()
        if not m.r(NET) >> 30 & 1:
            sys.exit("net.py: this design has no network")
        t = time.time()
        for addr, val in words:
            m.w(NETA, addr)
            m.w(NETD, val)
            for _ in range(200):                # (taken between the network's passes: 30 us at most)
                if not m.r(NET) >> 31:
                    break
            else:
                sys.exit("net.py: the weight at %d was not taken (is the output running?)" % addr)
        m.close()
        print("%d values put in, %.0f s" % (len(words), time.time() - t))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
