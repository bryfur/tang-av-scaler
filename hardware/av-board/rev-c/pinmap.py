"""Rev C's FPGA pin assignment: which SOM pin carries which signal.

The FPGA takes any signal on any I/O, so each group of signals (one chip's bus) takes the free
3.3 V I/O pins nearest that chip (floor.py's geometry), a clock input a clock-capable pin, and a
bus keeps the order its lines leave the chip along the connector (fewer crossings: gen_pcb.py
counts them). Dedicated pins (JTAG, RECONFIG_N, DONE, READY, the MODE straps, the transceivers,
the 5 V input) are fixed by the SOM. The result is written to the board (the receptacles' nets)
and to fpga/<rev>.cst, the Gowin constraints the gateware is built with.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floor  # noqa: E402
import som  # noqa: E402

PINS = som.pins()
# 3.3 V I/O banks (the SOM feeds banks 2-5 from its 3.3 V; bank 8 shares the DDR banks' supply)
IO_BANKS = {"2", "3", "4", "5"}
# I/O pins kept out of general use: PUDC_B (J20 pin 10, sampled at configuration). (The MODE
# straps and CFGBVS are bank 10's, outside IO_BANKS. The SPI_* and SSPI_* balls are configuration
# pins only in the SPI configuration modes; in MSPI mode, ours, they are I/O: the Console uses them
# for its SD card and SDRAM sockets.)
RESERVED = {("J20", 10)}


def fixed():
    """The SOM's dedicated and supply pins -> net (MODE straps, JTAG, configuration, power)."""
    out = {}
    for ref, pins in PINS.items():
        for pin, (net, use, _) in pins.items():
            if net == "GND":
                out[(ref, pin)] = "GND"
            elif net == "VBUS_SOM":
                out[(ref, pin)] = "+5V"
            elif net in ("DONE", "READY"):
                out[(ref, pin)] = "FPGA_" + net
    jtag = {"JTAG.TMS": "JTAG_TMS", "JTAG.TDO": "JTAG_TDO", "JTAG.TCK": "JTAG_TCK", "JTAG.TDI": "JTAG_TDI",
            "RECONFIG_N": "RECONFIG_N", "MODE0": "MODE0", "MODE1": "MODE1", "MODE2": "MODE2"}
    for ref, pins in PINS.items():
        for pin, (net, use, _) in pins.items():
            for k, v in jtag.items():
                if k in use.split():
                    out[(ref, pin)] = v
    assert sorted(v for v in out.values() if v.startswith(("JTAG", "MODE", "RECONFIG"))) == sorted(jtag.values()), out
    return out


def transceivers(lanes):
    """{lane: net prefix}: the lanes' TX pins -> <prefix>_P/_N; and REFCLK0 -> SER_REFCLK_P/_N."""
    out = {}
    for ref, pins in PINS.items():
        for pin, (net, _, _) in pins.items():
            for lane, prefix in lanes.items():
                if net == "Q0_L%d.TXP" % lane:
                    out[(ref, pin)] = prefix + "_P"
                elif net == "Q0_L%d.TXN" % lane:
                    out[(ref, pin)] = prefix + "_N"
            if net == "Q0_REFCLK0.P":
                out[(ref, pin)] = "SER_REFCLK_P"
            elif net == "Q0_REFCLK0.N":
                out[(ref, pin)] = "SER_REFCLK_N"
    return out


def is_clock(pin_info):
    """A true clock input: GCLKT, MGCLKT or SGCLKT (the P side of a clock pair takes a single-ended
    clock)."""
    return any("GCLKT" in f.split("/")[0] for f in pin_info[2].split())


def hungarian(cost):
    """The assignment of rows to columns (rows <= columns) of least total cost: [column of row i]."""
    n, m = len(cost), len(cost[0])
    INF = float("inf")
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [INF] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    out = [0] * n
    for j in range(1, m + 1):
        if p[j]:
            out[p[j] - 1] = j - 1
    return out


def _crosses(a, b, box):
    """Does segment a-b pass through the open box (x0, y0, x1, y1)? (Liang-Barsky)"""
    (ax, ay), (bx, by) = a, b
    t0, t1 = 0.0, 1.0
    for p, q in ((-(bx - ax), ax - box[0]), (bx - ax, box[2] - ax), (-(by - ay), ay - box[1]), (by - ay, box[3] - ay)):
        if p == 0:
            if q <= 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 >= t1:
                return False
    return True


def around(p, q, body):
    """The length of the shortest way from p to q that keeps out of body: a chip's pad box (its pads
    on its edges), the line passing its corners 0.5 mm out. A straight line when nothing is in the
    way."""
    if body is None:
        return math.hypot(q[0] - p[0], q[1] - p[1])
    inner = (body[0] + 0.3, body[1] + 0.3, body[2] - 0.3, body[3] - 0.3)
    corners = [(x, y) for x in (body[0] - 0.5, body[2] + 0.5) for y in (body[1] - 0.5, body[3] + 0.5)]
    nodes = [p] + corners + [q]
    best = {0: 0.0}
    todo = {0}
    while todo:                                  # Dijkstra on six nodes
        i = min(todo, key=best.get)
        todo.discard(i)
        if i == len(nodes) - 1:
            return best[i]
        for j in range(len(nodes)):
            if j != i and not _crosses(nodes[i], nodes[j], inner):
                d = best[i] + math.hypot(nodes[j][0] - nodes[i][0], nodes[j][1] - nodes[i][1])
                if d < best.get(j, 1e18):
                    best[j] = d
                    todo.add(j)
    return 1e9


def assign(groups, taken=None):
    """groups: [(name, {signal: (x, y) of its pin on the chip}, {signal: "clock"}[, body])] in
    priority order; body: the chip's pad box, when its pins are given (chip_pins).
    Clock inputs take the nearest free clock pins;
    the rest of a group take the free pins nearest the group (clock-capable pins kept for clocks,
    15 mm dearer), matched to the signals for the least total length, each line measured round the
    chip's body (a pin on its far side is reached round a corner): lines between two point sets
    matched so cross nowhere, so the bus leaves the connector untangled.
    Returns {(ref, pin): signal}."""
    taken = dict(taken or {})
    free = [(ref, pin) for ref, pins in PINS.items() for pin, info in pins.items()
            if som.ball(info[0]) and som.ball(info[0])[0] in IO_BANKS and (ref, pin) not in RESERVED
            and (ref, pin) not in taken]
    out = {}
    for g in groups:
        name, pos, special = g[:3]
        body = g[3] if len(g) > 3 else None

        def dist(rp, x, y):
            return around(floor.pin_xy(*rp), (x, y), body)
        for sig in [s for s in pos if special.get(s) == "clock"]:
            rp = min((rp for rp in free if is_clock(PINS[rp[0]][rp[1]])), key=lambda rp: dist(rp, *pos[sig]))
            out[rp] = sig
            free.remove(rp)
        rest = [s for s in pos if special.get(s) != "clock"]
        # (the nearest: by the way to the group's nearest pin)
        near = sorted(free, key=lambda rp: min(dist(rp, *pos[s]) for s in rest) +
                      (15.0 if is_clock(PINS[rp[0]][rp[1]]) else 0.0))
        near = near[:len(rest) + max(4, len(rest) // 4)]        # (a little choice for the matching)
        cols = hungarian([[dist(rp, *pos[s]) for rp in near] for s in rest])
        chosen = {near[c]: s for s, c in zip(rest, cols)}
        if body:
            chosen = untangle(chosen, pos, body)
        for rp, s in chosen.items():
            out[rp] = s
            free.remove(rp)
    return out


def untangle(chosen, pos, body):
    """The matched pins, each receptacle row's in the order of its signals round the chip: a row's
    lines then fan out without crossing. (The rows are 0.4 mm pitch: a line from the inner row
    cannot pass between the outer row's pads, so it leaves on the other layer; the two rows' lines
    do not meet.) The order round the chip starts square away from the receptacle; it runs the way
    the row's pins do."""
    cx, cy = (body[0] + body[2]) / 2, (body[1] + body[3]) / 2
    rows = {}
    for rp in chosen:
        rows.setdefault((rp[0], rp[1] % 2), []).append(rp)
    out = {}
    for (ref, _), pins in rows.items():
        x, y, angle = floor.connector(ref)
        upright = int(round(angle)) % 180 == 90
        away = (0.0 if x < cx else math.pi) if upright else (math.pi / 2 if y < cy else -math.pi / 2)

        def along(rp):
            return floor.pin_xy(*rp)[1 if upright else 0]

        def rel(p):
            return (math.atan2(p[1] - cy, p[0] - cx) - away - 0.4) % (2 * math.pi)
        ends = sorted((along((ref, n)), (ref, n)) for n in (1, 2, som.CONNECTORS[ref][1] - 1, som.CONNECTORS[ref][1]))
        sign = 1 if rel(floor.pin_xy(*ends[-1][1])) > rel(floor.pin_xy(*ends[0][1])) else -1
        sigs = sorted((chosen[rp] for rp in pins), key=lambda s: sign * rel(pos[s]))
        for rp, s in zip(sorted(pins, key=along), sigs):
            out[rp] = s
    return out


def write_cst(path, nets):
    """Gowin physical constraints: IO_LOC per signal (ball), LVCMOS33 on the 3.3 V banks."""
    lines = ["// %s: FPGA pins (generated by rev-c/pinmap.py from the board's SOM nets)" % os.path.basename(path)]
    for (ref, pin), sig in sorted(nets.items(), key=lambda kv: kv[1]):
        info = PINS[ref][pin]
        b = som.ball(info[0])
        if not b or sig in ("GND",):
            continue
        name = sig.lower()
        lines.append('IO_LOC "%s" %s;  // %s pin %d, bank %s%s' % (name, b[1], ref, pin, b[0], ", " + info[2].split("/")[0] if info[2] else ""))
        if b[0] in IO_BANKS:
            lines.append('IO_PORT "%s" IO_TYPE=LVCMOS33;' % name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write("\n".join(lines) + "\n")
