#!/usr/bin/env python3
"""Route a Specctra DSN on DeepPCB (deeppcb.ai, the cloud router) and fetch the result as a session.

    python3 deeppcb.py run av-board.dsn out.ses [--minutes 30]   # upload, route, poll, download
    python3 deeppcb.py follow BOARD_ID out.ses [--minutes 30]     # route an uploaded board
    python3 deeppcb.py status BOARD_ID
    python3 deeppcb.py fetch BOARD_ID out.ses
    python3 deeppcb.py stop BOARD_ID

The key comes from $DEEPPCB_API_KEY or ~/.config/deeppcb/key (never from this repository). Routing
keeps the existing wiring (CurrentProtectedWiring: the BGA fanout, plane vias and chains that
gen_pcb.py lays down) and does no placement. DeepPCB bills per minute of routing (its site says
0.5 credits, a board reported 1.0); the --minutes cap bounds the cost. API: https://api.deeppcb.ai/v1/scalar/deeppcb (DeepPCB Public API v1).

Before routing, the board is resubmitted in DeepPCB's own JSON with what a DSN cannot say: the
board-edge clearance (DEEPPCB_EDGE_MM, 0.3) and the differential pairs (nets named X_P/X_N);
DEEPPCB_TUNE=0 routes the DSN as it is.

gen_pcb.py takes the session with SES=out.ses python3 gen_pcb.py --route.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "https://api.deeppcb.ai/api/v1"


def key():
    k = os.environ.get("DEEPPCB_API_KEY")
    if not k:
        with open(os.path.expanduser("~/.config/deeppcb/key")) as f:
            k = f.read().strip()
    return k


def call(method, path, body=None, ctype=None, raw=False):
    headers = {"x-deeppcb-api-key": key(), "Accept": "application/json, text/plain, */*"}
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(API + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit("%s %s: HTTP %d %s" % (method, path, e.code, e.read().decode(errors="replace")[:2000]))
    if raw:
        return data
    text = data.decode()
    try:
        return json.loads(text)
    except ValueError:
        return text


def multipart(fields, files):
    b = "----deeppcb" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, k, v)).encode())
    for k, path in files.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                    "Content-Type: application/octet-stream\r\n\r\n" % (b, k, os.path.basename(path))).encode())
        out.append(open(path, "rb").read())
        out.append(b"\r\n")
    out.append(("--%s--\r\n" % b).encode())
    return b"".join(out), "multipart/form-data; boundary=" + b


def board(board_id):
    """The board with its workflows; just after the upload it can take a moment to appear."""
    for _ in range(20):
        try:
            return call("GET", "/boards/%s" % board_id)
        except SystemExit as e:
            if "HTTP 404" not in str(e):
                raise
            time.sleep(15)
    return call("GET", "/boards/%s" % board_id)


def summary(b):
    r = b.get("result") or {}
    return "status %s, %s of %s air wires connected, %s nets of %s, %s min used" % (
        b.get("boardStatus"), r.get("airWiresConnected"), r.get("totalAirWires"), r.get("numNetsCompleted"),
        r.get("numNets"), round(b.get("workflowBurnedMinutes") or 0, 1))


def latest_revision(b):
    revs = [rv for wf in (b.get("workflows") or []) + [b.get("workflow") or {}] for rv in (wf or {}).get("revisions") or []]
    return max((rv.get("revisionNumber") for rv in revs if rv.get("revisionNumber") is not None), default=None)


def fetch(board_id, out):
    b = board(board_id)
    rev = latest_revision(b)
    q = "?type=SesFile" + ("&revision=%d" % rev if rev is not None else "")
    data = call("GET", "/boards/%s/revision-artifact%s" % (board_id, q), raw=True)
    if data[:1] == b'"':                    # a JSON string (the file's text, or a URL to it)
        s = json.loads(data.decode())
        data = urllib.request.urlopen(s, timeout=120).read() if s.startswith("http") else s.encode()
    with open(out, "wb") as f:
        f.write(data)
    print("revision %s -> %s (%d bytes)" % (rev, out, len(data)))


def run(dsn, out, minutes):
    # The API insists on a webhook (it posts status, designs and billing there). We poll instead, so
    # point it back at DeepPCB's own site: nothing goes to a third party.
    hook = os.environ.get("DEEPPCB_WEBHOOK", "https://app.deeppcb.ai/")
    body, ctype = multipart({"routingType": "CurrentProtectedWiring", "boardName": os.path.basename(dsn),
                             "requestId": uuid.uuid4().hex, "webhookUrl": hook,
                             "webhookToken": uuid.uuid4().hex}, {"dsnFile": dsn})
    r = call("POST", "/boards", body, ctype)
    board_id = r if isinstance(r, str) else (r.get("boardId") or r.get("id"))
    board_id = board_id.strip('"')
    print("board", board_id)
    if os.environ.get("DEEPPCB_TUNE", "1") == "1":
        # resubmit as DeepPCB JSON with the edge clearance and the differential pairs
        board(board_id)
        tuned = tune(board_id, os.path.splitext(out)[0] + ".deeppcb.json", None, float(os.environ.get("DEEPPCB_EDGE_MM", "0.3")))
        board_id = submit_json(tuned)
        print("tuned board", board_id)
    follow(board_id, out, minutes)


def tune(board_id, out_json, pairs, edge_mm):
    """DeepPCB's own JSON of an uploaded board, with what the DSN cannot carry added: a boundary
    clearance and differential pairs (net names ending _P/_N, or given)."""
    j = call("GET", "/boards/%s/json" % board_id)
    if isinstance(j, str):
        j = json.loads(j)
    res = j["resolution"]
    per_mm = {"mm": 1, "um": 1000, "mil": 1 / 0.0254, "inch": 1 / 25.4, "cm": 0.1}[res["unit"]] * res["value"]
    j["boundary"]["clearance"] = int(round(edge_mm * per_mm))
    names = {n.get("id"): n for n in j.get("nets", [])}
    found = []
    for n in names:
        if n.endswith("_P") and n[:-2] + "_N" in names:
            found.append((n, n[:-2] + "_N"))
    j["differentialPairs"] = [{"netId1": a_, "netId2": b_} for a_, b_ in (pairs or found)]
    with open(out_json, "w") as f:
        json.dump(j, f)
    print("boundary clearance %s (%.2f mm), %d differential pairs: %s" % (
        j["boundary"]["clearance"], edge_mm, len(j["differentialPairs"]),
        ", ".join(a_[:-2] for a_, _ in (pairs or found))))
    return out_json


def submit_json(path):
    hook = os.environ.get("DEEPPCB_WEBHOOK", "https://app.deeppcb.ai/")
    body, ctype = multipart({"routingType": "CurrentProtectedWiring", "boardName": os.path.basename(path),
                             "requestId": uuid.uuid4().hex, "webhookUrl": hook,
                             "webhookToken": uuid.uuid4().hex}, {"jsonFile": path})
    r = call("POST", "/boards", body, ctype)
    return (r if isinstance(r, str) else (r.get("boardId") or r.get("id"))).strip('"')


def follow(board_id, out, minutes):
    """Start routing an uploaded board, poll it until it ends, fetch the session."""
    b = board(board_id)
    print("cost per minute:", b.get("creditsCostPerMinute"), "credits; cap", minutes, "minutes")
    for k in ("routingEligibility", "warnings", "anomalies", "routingAnomalies"):
        if b.get(k):
            print(k, json.dumps(b[k])[:300])
    batch = call("GET", "/boards/%s/recommended-max-batch-timeout" % board_id)
    batch = int(batch.get("recommendedMaxBatchTimeout") or batch.get("value") or 60) if isinstance(batch, dict) \
        else int(float(str(batch).strip('"') or 60))
    print("max batch timeout", batch, "s")
    call("PATCH", "/boards/%s/confirm" % board_id,
         json.dumps({"jobType": "Routing", "routingType": "CurrentProtectedWiring", "timeout": minutes,
                     "maxBatchTimeout": max(batch, 11), "responseBoardFormat": 4}).encode(), "application/json")
    last = ""
    while True:
        time.sleep(30)
        b = board(board_id)
        s = summary(b)
        if s != last:
            print(time.strftime("%H:%M:%S"), s, flush=True)
            last = s
        if b.get("boardStatus") in ("Done", "Failed", "Stopped", "StopFailed"):
            break
    fetch(board_id, out)


def main():
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    if a[0] == "run":
        minutes = int(a[a.index("--minutes") + 1]) if "--minutes" in a else 30
        run(a[1], a[2], minutes)
    elif a[0] == "follow":
        minutes = int(a[a.index("--minutes") + 1]) if "--minutes" in a else 30
        follow(a[1], a[2], minutes)
    elif a[0] == "status":
        b = board(a[1])
        print(summary(b), "latest revision", latest_revision(b))
    elif a[0] == "fetch":
        fetch(a[1], a[2])
    elif a[0] == "stop":
        print(call("PATCH", "/boards/%s/stop" % a[1], b"{}", "application/json"))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
