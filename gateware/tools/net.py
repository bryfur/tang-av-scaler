#!/usr/bin/env python3
"""net.py: the scaler's network (rtl/cnn.v; docs/cnn-upscaler.md) on the board.

  net.py status              is it there, is it on, rows it was late for
  net.py on | off            the setting (the link's: the web page's "Upscaler")
  net.py load MODEL.json     another network of the same shape (3 x 3: 1 -> 8 -> 8 -> 4) put into the
                             running design through the monitor: its weights, biases and shifts
                             (sim/model.py net_words()).  It is there until the FPGA is loaded
                             again (the design's own is sim/cnn/t8s.json); check it with
                             NET=MODEL.json tools/boardcheck.py

The board: AVX_HOST (default 192.168.1.112); the monitor as tools/avb.py finds it (AVB_TTY)."""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../sim"))
HOST = os.environ.get("AVX_HOST", "192.168.1.112")
os.environ.setdefault("AVB_TTY", "tcp:%s:2323" % HOST)
NET, NETA, NETD, NETS = 0x44, 0x45, 0x46, 0x47


def video():
    return json.load(urllib.request.urlopen("http://%s/api/video" % HOST, timeout=5))


def main():
    a = sys.argv[1:]
    if not a or a[0] == "status":
        v = video()
        n = v.get("net", {})
        print("the network: %s; the setting: %s; rows it was late for: %d" % (
            "in this design" if n.get("there") else "NOT in this design", "on" if v["set"].get("net") else "off", n.get("under", 0)))
    elif a[0] in ("on", "off"):
        urllib.request.urlopen("http://%s/api/video" % HOST, ("net=%d" % (a[0] == "on")).encode(), timeout=10).read()
        time.sleep(2)
        main_status = video()
        print("the setting: %s" % ("on" if main_status["set"].get("net") else "off"))
    elif a[0] == "load":
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
