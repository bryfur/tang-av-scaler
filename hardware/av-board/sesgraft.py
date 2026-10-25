#!/usr/bin/env python3
"""Take some nets' copper from a Specctra session and add it to a routed board, leaving the rest
of the board as it is (a finishing run on DeepPCB for a few nets, the TMDS pairs).

    python3 sesgraft.py BOARD SES PREFIX[,PREFIX]   # e.g. TMDS_

The session is imported into a scratch copy (KiCad's import replaces all copper), the nets'
tracks and vias are read from there, and added to BOARD in a fresh process (after a session
import pcbnew cannot list a board's tracks); the zones are refilled.
"""
import json
import os
import subprocess
import sys
import tempfile


def read(board, ses, prefixes, out):
    import pcbnew
    from pcbnew import ToMM
    b = pcbnew.LoadBoard(board)
    removed = list(b.GetTracks())           # (kept referenced: freeing them makes pcbnew crash later)
    for t in removed:
        b.Remove(t)
    if not pcbnew.ImportSpecctraSES(b, ses):
        raise SystemExit("SES import failed")
    items = []
    for t in b.Tracks():
        if not t.GetNetname().startswith(prefixes):
            continue
        if t.GetClass() == "PCB_VIA":
            items.append({"via": [ToMM(t.GetPosition().x), ToMM(t.GetPosition().y)], "net": t.GetNetname(),
                          "d": ToMM(t.GetWidth()), "drill": ToMM(t.GetDrillValue())})
        else:
            items.append({"layer": b.GetLayerName(t.GetLayer()), "net": t.GetNetname(), "w": ToMM(t.GetWidth()),
                          "a": [ToMM(t.GetStart().x), ToMM(t.GetStart().y)], "b": [ToMM(t.GetEnd().x), ToMM(t.GetEnd().y)]})
    json.dump(items, open(out, "w"))


def add(board, inp):
    import pcbnew
    from pcbnew import VECTOR2I, FromMM
    items = json.load(open(inp))
    b = pcbnew.LoadBoard(board)
    for it in items:
        n = b.FindNet(it["net"])
        if "via" in it:
            v = pcbnew.PCB_VIA(b)
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetPosition(VECTOR2I(FromMM(it["via"][0]), FromMM(it["via"][1])))
            v.SetWidth(FromMM(it["d"]))
            v.SetDrill(FromMM(it["drill"]))
            v.SetNet(n)
            b.Add(v)
        else:
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(VECTOR2I(FromMM(it["a"][0]), FromMM(it["a"][1])))
            t.SetEnd(VECTOR2I(FromMM(it["b"][0]), FromMM(it["b"][1])))
            t.SetWidth(FromMM(it["w"]))
            t.SetLayer(b.GetLayerID(it["layer"]))
            t.SetNet(n)
            b.Add(t)
    pcbnew.SaveBoard(board, b)
    print("grafted %d tracks, %d vias" % (sum("via" not in i for i in items), sum("via" in i for i in items)))


def fill(board):
    import pcbnew
    b = pcbnew.LoadBoard(board)
    b.BuildConnectivity()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(board, b)


if __name__ == "__main__":
    a = sys.argv[1:]
    me = os.path.abspath(__file__)
    if a[:1] == ["--read"]:
        read(a[1], a[2], tuple(a[3].split(",")), a[4])
    elif a[:1] == ["--add"]:
        add(a[1], a[2])
    elif a[:1] == ["--fill"]:
        fill(a[1])
    elif len(a) == 3:
        board, ses, prefixes = a
        with tempfile.TemporaryDirectory() as tmp:
            scratch, items = os.path.join(tmp, "s.kicad_pcb"), os.path.join(tmp, "items.json")
            subprocess.run(["cp", board, scratch], check=True)
            subprocess.run([sys.executable, me, "--read", scratch, ses, prefixes, items], check=True)
            subprocess.run([sys.executable, me, "--add", board, items], check=True)
            subprocess.run([sys.executable, me, "--fill", board], check=True)
    else:
        raise SystemExit(__doc__)
