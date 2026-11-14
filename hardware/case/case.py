"""A 3D-printable case for the AV board rev C-B (the scaler), generated from the board itself.

    ~/tools/cad-venv/bin/python hardware/case/case.py          # -> hardware/case/out/*.stl, case.step

Positions come from the routed board (../av-board/rev-cb/av-board-cb.kicad_pcb: its outline, the
four M2.5 holes H1-H4, the jacks, buttons and LEDs) and the SOM's place from ../av-board/rev-c/
floor.py, so the case follows the board if a part moves. Heights and how far a part reaches past
the board's edge are measured on the parts' 3D models (check.py, KiCad's GLB export) or, where the
model is placed wrongly in KiCad (the HDMI receptacle's and the USB-C's models sit 2-7 mm off their
footprints), taken from the footprint's courtyard and the part's name (HDMI ... H6.1).

The parts (all print without supports):

    base     floor + side walls, four standoffs under the board's holes; floor down
    lid      top plate, vents over the SOM's heatsink, a 40 mm fan under it over the SOM's memory,
             four pillars that press the board onto the standoffs, guides for the buttons, tubes
             over the LEDs; printed upside down
    back     the back panel: RCA x 5, USB-C power, HDMI; outside face down
    front    the front panel: the XIAO's USB-C; outside face down
    button   x 3, a plunger from the lid to each tact switch, held by a bayonet; head down

Assembly: hold the back panel against the jacks (their barrels and the HDMI's shell go into its
holes), lower board + panel into the base (the panel into its grooves, the board onto the
standoffs), slide the front panel into its grooves, put the buttons into the lid's guides from
above (tab along the keyway) and turn each a quarter, put the lid on, turn the case over and fit
four M2.5 x 16 screws from below: each passes the floor, a standoff and the board and threads into
a lid pillar (self-tapping into the plastic, or an M2.5 heat-set insert with INSERT = True). For the LEDs, push a 24 mm piece of clear 1.75 mm
filament into each tube from above. The XIAO's antenna sticks to the inside of the lid.

Coordinates: X = board x - CX, Y = CY - board y (the back edge with the jacks at +Y), Z up with
0 at the board's underside. Lengths in mm.
"""
import math
import os
import re
import sys

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
AV = os.path.join(HERE, "..", "av-board")
PCB = os.path.join(AV, "rev-cb", "av-board-cb.kicad_pcb")
sys.path.insert(0, os.path.join(AV, "rev-c"))
import floor  # noqa: E402
import som  # noqa: E402

# ---- the board -------------------------------------------------------------------------------

def footprints(path=PCB):
    """{ref: (x, y, angle)} for every footprint, and the Edge.Cuts bounding box."""
    s = open(path).read()
    fps = {}
    for m in re.finditer(r'\n\t\(footprint "[^"]+"', s):
        blk = s[m.start():m.start() + 4000]
        at = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', blk)
        ref = re.search(r'\(property "Reference" "([^"]+)"', blk).group(1)
        fps[ref] = (float(at.group(1)), float(at.group(2)), float(at.group(3) or 0))
    xs, ys = [], []
    for m in re.finditer(r'\(gr_line\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)'
                         r'[\s\S]{0,200}?\(layer "Edge.Cuts"\)', s):
        xs += [float(m.group(1)), float(m.group(3))]
        ys += [float(m.group(2)), float(m.group(4))]
    return fps, (min(xs), min(ys), max(xs), max(ys))


FP, (BX0, BY0, BX1, BY1) = footprints()
CX, CY = (BX0 + BX1) / 2, (BY0 + BY1) / 2
T_PCB = 1.6                       # the board (JLC04161H-7628)
TOP = T_PCB                       # the board's top face

# measured on the 3D models (check.py prints them), heights from the board's underside
RCA_Z = 8.2                       # the RCA barrels' axis (8.3 mm across, 47.94 = 2.06 mm past the edge)
USBC_Z = TOP + 1.63               # TYPE-C-31-M-12: 8.94 x 3.26 shell on the board, mouth 0.6 mm past
HDMI_Z0, HDMI_Z1 = TOP, TOP + 6.1 # HDMI-001 (H6.1), its mouth 2.1 mm past the edge (courtyard)
SWITCH_TOP = 3.10                 # TS-1187A, 1.5 mm tall
LED_TOP = 2.29                    # 0603
UNDER = 3.63                      # the deepest through-hole lead below the board (HDMI shell legs)
# the XIAO in its sockets: 8.5 mm female headers, the module's own 2.5 mm male-header spacer,
# a 1.0-1.2 mm board, its USB-C (3.2 mm) on top: the receptacle's centre about 15.3 mm up. Not on
# a model (the XIAO has none here): the front panel's opening is tall enough for +-1.5 mm
XIAO_USB_Z = 15.3

# ---- the case ---------------------------------------------------------------------------------

GAP = 0.5                         # board edge to side wall
WALL = 3.0                        # side walls
FLOOR = 2.0
STANDOFF = UNDER + 1.4            # board underside above the floor: 5.0
INNER = 24.0                      # board top to the lid's underside (the SOM's heatsink ~17, a
                                  # Dupont housing on a header 16.5: room for both and air)
LID_T = 2.5
PANEL_T = 2.0
PANEL_GAP = 0.2                   # panel to groove, each side
GROOVE_W = PANEL_T + 2 * PANEL_GAP
GROOVE_SIDE = 1.5                 # into the side walls
GROOVE_FLOOR = 1.0
GROOVE_LID = 1.2
LIP = 1.5                         # side walls, floor and lid past the panels' outside faces
CORNER_R = 3.0
BACK_OUT = 47.8                   # back panel's outside face (board y): the HDMI mouth 47.9
BACK_IN = BACK_OUT + PANEL_T      # 49.8, 0.2 mm in front of the board's edge
# the XIAO's USB-C reaches ~1-1.5 mm past the board's front edge: the front panel stands clear of
# it, so it slides down its grooves with the XIAO fitted (the plug's overmold reaches in through the
# opening, the receptacle 2-3 mm behind the outside face)
FRONT_IN = BY1 + 1.8
FRONT_OUT = FRONT_IN + PANEL_T

Z_FLOOR = -STANDOFF               # floor's top
Z_BOT = Z_FLOOR - FLOOR
Z_LID = TOP + INNER               # lid's underside
Z_TOP = Z_LID + LID_T

X_IN0, X_IN1 = BX0 - GAP, BX1 + GAP
X_OUT0, X_OUT1 = X_IN0 - WALL, X_IN1 + WALL
Y_OUT0, Y_OUT1 = BACK_OUT - LIP, FRONT_OUT + LIP     # board y

# fasteners: M2.5 x 16 from below through floor, standoff and board into a lid pillar
SCREW_CLEAR = 2.9
HEAD_D, HEAD_H = 5.2, 2.5         # counterbore for a pan / cheese head
INSERT = False                    # True: holes for M2.5 heat-set inserts (3.5 x 4 mm)
PILOT = 2.2                       # self-tapping M2.5 into the plastic
INSERT_D, INSERT_L = 3.4, 4.5
PILLAR_D = 6.0
STANDOFF_D = 6.5
HOLES = ["H1", "H2", "H3", "H4"]

# buttons: a round plunger in a round guide, a head above the lid and a tab below the guide's end:
# put in from the top with the tab in the guide's keyway, then turned a quarter: held both ways
# (the head stops it falling in, the tab pulling out), so the lid comes off with its buttons
KEY = 3.4                         # plunger
KEY_HOLE = KEY + 0.5
HEAD_D, HEAD_T = 7.0, 1.6         # covers the keyway (switch pitch 8 mm)
SLEEVE = 7.0                      # guide's outside
SLEEVE_L = 8.0                    # below the lid
KEY_PROUD = 0.8                   # head above the lid at rest (the switch travels 0.25)
KEY_LIFT = 1.0                    # free travel up before the tab meets the guide
TAB_R, TAB_W, TAB_T = 3.15, 1.8, 1.6
KEYWAY_R, KEYWAY_W = 3.45, 2.2    # toward +X; the tab rests toward the back
BUTTONS = [("SW1", "K1"), ("SW2", "K2"), ("SW3", "RCFG")]

# the SOM's heatsink, on the FPGA in the SOM's front half (the board photo, img/av-board-cb-photo.jpg,
# measured against the SOM's holes: its back edge ~y 105; the DDR3 chips behind it, ~y 89-103):
# x0, x1, y0, y1 on the board and its top. Not measured on the part: check it before printing
HEATSINK = (141.0, 169.0, 105.0, 131.0)
HEATSINK_TOP = TOP + 17.0
# a 5 V fan inside, hung under the lid over the SOM's memory, beside the heatsink (the lid is 7 mm
# above the heatsink: no room over it), blowing down through a round grille; the warm air leaves by
# the slots over the heatsink and the side vents. M3 x 12 screws from the top through countersunk
# holes cut their thread in the fan's corner holes. Its wire plugs onto J13 pins 4 (GND) and 5
# (5 V, behind a 0.2 A resettable fuse). FAN = 0: no fan
FAN = 40                          # 40, 30 or 25 mm square, FAN_T thick
FAN_T = 10.0
FAN_HOLES = {25: 20.0, 30: 24.0, 40: 32.0}     # the fans' hole spacing
FAN_GRILLE = {25: 23.0, 30: 28.0, 40: 37.0}
FAN_HUB = {25: 9.0, 30: 11.0, 40: 14.0}        # the motor's hub: no air there
FAN_GAP = 2.5                     # fan to heatsink, sideways
FAN_AT = (floor.SOM_AT[0], HEATSINK[2] - FAN_GAP - FAN / 2)
FAN_SCREW, FAN_CSK = 3.4, 6.6

# LEDs: a tube from the lid to 1 mm above each, for a piece of 1.75 mm clear filament
PIPE_ID, PIPE_OD = 1.9, 3.6
LEDS = [("D2", "STAT"), ("D4", "DONE"), ("D5", "RDY")]

# back panel: (ref, label, kind)
RCA_HOLE = 11.0                   # an RCA plug's shell passes (the barrels are recessed 0.1 mm)
USBC_HOLE = (12.8, 7.0, 3.0)      # w, h, r: a USB-C plug's overmold (spec max 12.35 x 6.5)
HDMI_HOLE = (16.0, 7.4, 1.0)      # around the receptacle's shell (15.0 x 6.1)
XIAO_HOLE = (13.0, 9.4, 3.0)      # the XIAO's USB-C plug, +-1.5 mm in height
BACK = [("J1", "Y"), ("J2", "Pb"), ("J3", "Pr"), ("J15", "5V"), ("J4", "L"), ("J5", "R"), ("J6", "HDMI")]

FONT = "DejaVu Sans"
ENGRAVE = 0.4


def X(x):
    return x - CX


def Y(y):
    return CY - y


def box(x0, x1, y0, y1, z0, z1):
    """An axis-aligned box from board coordinates (y0 < y1 in board y)."""
    return (cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((X(x0), Y(y1), z0)))


def cyl(x, y, d, z0, z1):
    return cq.Workplane("XY").circle(d / 2).extrude(z1 - z0).translate((X(x), Y(y), z0))


def rrect_y(x, z, w, h, r, y0, y1):
    """A rounded rectangle (w along x, h along z) through y0..y1, as a hole through a panel."""
    r = min(r, w / 2, h / 2)
    sk = cq.Sketch().rect(w, h).vertices().fillet(r) if r > 0 else cq.Sketch().rect(w, h)
    return (cq.Workplane("XZ").placeSketch(sk).extrude(-(y1 - y0))
            .translate((X(x), Y(y1), z)))


def cyl_y(x, z, d, y0, y1):
    return cq.Workplane("XZ").circle(d / 2).extrude(-(y1 - y0)).translate((X(x), Y(y1), z))


def text_cut(body, txt, size, origin, xdir, normal, depth=ENGRAVE):
    """Engrave txt into body's face at origin (case coordinates), reading along xdir."""
    pl = cq.Plane(origin=origin, xDir=xdir, normal=normal)
    t = cq.Workplane(pl).text(txt, size, -depth, font=FONT, kind="bold", halign="center", valign="center")
    return body.cut(t)


def at(ref):
    return FP[ref][0], FP[ref][1]


def som_box():
    sx, sy = som.SIZE
    if floor.SOM_ANGLE % 180:
        sx, sy = sy, sx
    return (floor.SOM_AT[0] - sx / 2, floor.SOM_AT[0] + sx / 2,
            floor.SOM_AT[1] - sy / 2, floor.SOM_AT[1] + sy / 2)


# ---- parts ------------------------------------------------------------------------------------

def outline(z0, z1):
    w, l = X_OUT1 - X_OUT0, Y_OUT1 - Y_OUT0
    return (cq.Workplane("XY").rect(w, l).extrude(z1 - z0).edges("|Z").fillet(CORNER_R)
            .translate((X((X_OUT0 + X_OUT1) / 2), Y((Y_OUT0 + Y_OUT1) / 2), z0)))


def grooves(z0, z1, side, floor_d=0.0):
    """The panels' grooves: into the side walls (side) and down into z0 by floor_d."""
    g = None
    for yo in (BACK_OUT, FRONT_IN):
        y0, y1 = yo - PANEL_GAP, yo + PANEL_T + PANEL_GAP
        s = box(X_IN0 - side, X_IN1 + side, y0, y1, z0 - floor_d, z1)
        g = s if g is None else g.union(s)
    return g


def base():
    b = outline(Z_BOT, Z_LID)
    b = b.cut(box(X_IN0, X_IN1, Y_OUT0 - 1, Y_OUT1 + 1, Z_FLOOR, Z_LID + 1))
    b = b.cut(grooves(Z_FLOOR, Z_LID + 1, GROOVE_SIDE, GROOVE_FLOOR))
    for h in HOLES:
        x, y = at(h)
        b = b.union(cyl(x, y, STANDOFF_D, Z_FLOOR - 0.5, 0))
        b = b.cut(cyl(x, y, SCREW_CLEAR, Z_BOT - 1, 1))
        b = b.cut(cyl(x, y, HEAD_D, Z_BOT - 1, Z_BOT + HEAD_H))
    # side vents: slots low in both walls, above the board (the air in; out through the lid)
    for y in range(60, 141, 6):
        for x0 in (X_OUT0 - 1, X_IN1 - 0.1):
            b = b.cut(box(x0, x0 + WALL + 1.1, y - 1.0, y + 1.0, TOP + 3.0, TOP + 12.0))
    # feet: recesses for 10 mm stick-on bumpers
    for x in (CX - 38, CX + 38):
        for y in (Y_OUT0 + 10, Y_OUT1 - 10):
            b = b.cut(cyl(x, y, 10.5, Z_BOT - 1, Z_BOT + 0.6))
    return b


def lid():
    l = outline(Z_LID, Z_TOP)
    # locating strips inside the side walls
    for x0 in (X_IN0 + 0.2, X_IN1 - 0.2 - 1.6):
        l = l.union(box(x0, x0 + 1.6, BACK_IN + 3, FRONT_IN - 3, Z_LID - 2.0, Z_LID))
    l = l.cut(grooves(Z_LID - 3, Z_LID + GROOVE_LID, GROOVE_SIDE))
    for h in HOLES:
        x, y = at(h)
        l = l.union(cyl(x, y, PILLAR_D, TOP, Z_LID + 0.1))
        if INSERT:
            l = l.cut(cyl(x, y, INSERT_D, TOP - 1, TOP + INSERT_L))
            l = l.cut(cyl(x, y, 2.0, TOP - 1, TOP + 12))
        else:
            l = l.cut(cyl(x, y, PILOT, TOP - 1, TOP + 12))
    # vents over the heatsink: slots front to back
    hx0, hx1, hy0, hy1 = HEATSINK
    n = int((hx1 - hx0 + 4) // 4)
    for i in range(n):
        x = (hx0 + hx1) / 2 + (i - (n - 1) / 2) * 4.0
        l = l.cut(box(x - 1.0, x + 1.0, hy0 + 1.0, hy1 - 2.0, Z_LID - 1, Z_TOP + 1))
    if FAN:
        l = fan_mount(l, *FAN_AT)
    # buttons: round guides with a keyway
    for ref, _ in BUTTONS:
        x, y = at(ref)
        l = l.union(cyl(x, y, SLEEVE, Z_LID - SLEEVE_L, Z_LID + 0.1))
        l = l.cut(cyl(x, y, KEY_HOLE, Z_LID - SLEEVE_L - 1, Z_TOP + 1))
        l = l.cut(box(x, x + KEYWAY_R, y - KEYWAY_W / 2, y + KEYWAY_W / 2, Z_LID - SLEEVE_L - 1, Z_TOP + 1))
    # LEDs: light pipes
    for ref, _ in LEDS:
        x, y = at(ref)
        l = l.union(cyl(x, y, PIPE_OD, LED_TOP + 1.0, Z_LID + 0.1))
        l = l.cut(cyl(x, y, PIPE_ID, LED_TOP + 0.5, Z_TOP + 1))
    # labels on top
    up = (0, 0, 1)
    for ref, name in BUTTONS:
        x, y = at(ref)
        l = text_cut(l, name, 2.4, (X(x), Y(y + HEAD_D / 2 + 2.4), Z_TOP), (1, 0, 0), up)
    for ref, name in LEDS:
        x, y = at(ref)
        l = text_cut(l, name, 2.2, (X(x), Y(y - 3.0), Z_TOP), (1, 0, 0), up)
    return l


def fan_mount(l, cx, cy):
    """The fan's grille and its four countersunk screw holes, centred on (cx, cy)."""
    r, hub, a = FAN_GRILLE[FAN] / 2, FAN_HUB[FAN] / 2, FAN_HOLES[FAN] / 2
    z0, z1 = Z_LID - 1, Z_TOP + 1
    hole = cyl(cx, cy, 2 * r, z0, z1).cut(cyl(cx, cy, 2 * hub, z0 - 1, z1 + 1))
    # one ring and four spokes (on the diagonals, toward the screws) hold the hub
    ring = (r + hub) / 2
    hole = hole.cut(cyl(cx, cy, 2 * ring + 1.4, z0 - 1, z1 + 1).cut(cyl(cx, cy, 2 * ring - 1.4, z0 - 2, z1 + 2)))
    for ang in (45, 135):
        spoke = (cq.Workplane("XY").rect(2 * r + 2, 1.8).extrude(z1 - z0 + 2)
                 .rotate((0, 0, 0), (0, 0, 1), ang).translate((X(cx), Y(cy), z0 - 1)))
        hole = hole.cut(spoke)
    l = l.cut(hole)
    for sx in (-a, a):
        for sy in (-a, a):
            l = l.cut(cyl(cx + sx, cy + sy, FAN_SCREW, z0, z1))
            d = (FAN_CSK - FAN_SCREW) / 2                       # 90 degree countersink
            csk = (cq.Workplane("XY").circle(FAN_SCREW / 2).workplane(offset=d).circle(FAN_CSK / 2).loft()
                   .translate((X(cx + sx), Y(cy + sy), Z_TOP - d)))
            l = l.cut(csk).cut(cyl(cx + sx, cy + sy, FAN_CSK, Z_TOP - 0.01, Z_TOP + 1))
    return l


def fan_box():
    """The fan's volume, for check.py and render.py: (x0, x1, y0, y1, z0, z1) on the board."""
    cx, cy = FAN_AT
    return (cx - FAN / 2, cx + FAN / 2, cy - FAN / 2, cy + FAN / 2, Z_LID - FAN_T, Z_LID)


def panel(y_out, y_in):
    return box(X_IN0 - GROOVE_SIDE + PANEL_GAP, X_IN1 + GROOVE_SIDE - PANEL_GAP, min(y_out, y_in), max(y_out, y_in),
               Z_FLOOR - GROOVE_FLOOR + PANEL_GAP, Z_LID + GROOVE_LID - PANEL_GAP)


def back():
    p = panel(BACK_OUT, BACK_IN)
    y0, y1 = BACK_OUT - 1, BACK_IN + 1
    lz = RCA_Z + RCA_HOLE / 2 + 4.5
    for ref, label in BACK:
        x, _ = at(ref)
        if ref == "J15":
            w, h, r = USBC_HOLE
            p = p.cut(rrect_y(x, USBC_Z, w, h, r, y0, y1))
        elif ref == "J6":
            w, h, r = HDMI_HOLE
            p = p.cut(rrect_y(x, (HDMI_Z0 + HDMI_Z1) / 2, w, h, r, y0, y1))
        else:
            p = p.cut(cyl_y(x, RCA_Z, RCA_HOLE, y0, y1))
        # read from behind the case: +Y outward, so text runs along -X
        p = text_cut(p, label, 3.5, (X(x), Y(BACK_OUT), lz), (-1, 0, 0), (0, 1, 0))
    return p


def front():
    p = panel(FRONT_OUT, FRONT_IN)
    x = (at("J11")[0] + at("J12")[0]) / 2
    w, h, r = XIAO_HOLE
    p = p.cut(rrect_y(x, XIAO_USB_Z, w, h, r, FRONT_IN - 1, FRONT_OUT + 1))
    p = text_cut(p, "ESP USB", 3.0, (X(x), Y(FRONT_OUT), XIAO_USB_Z + h / 2 + 3.5), (1, 0, 0), (0, -1, 0))
    tx = (x + XIAO_HOLE[0] / 2 + X_IN1) / 2 + 3
    p = text_cut(p, "tang-av-scaler", 5.5, (X(tx), Y(FRONT_OUT), 15.5), (1, 0, 0), (0, -1, 0))
    p = text_cut(p, "AV board rev C-B", 3.0, (X(tx), Y(FRONT_OUT), 8.5), (1, 0, 0), (0, -1, 0))
    return p


def button(ref):
    """A plunger standing on its switch, as fitted: head above the lid, tab turned toward the back
    and 1 mm below the guide's end."""
    x, y = at(ref)
    z_head = Z_TOP + KEY_PROUD
    k = cyl(x, y, KEY, SWITCH_TOP, z_head + 0.1).union(cyl(x, y, HEAD_D, z_head, z_head + HEAD_T))
    tab_top = Z_LID - SLEEVE_L - KEY_LIFT
    # the tab, its top bevelled 45 degrees from just outside the guide's hole, so it prints head down
    # without support; it still cannot pass the hole (r 1.95) but by the keyway
    r0 = KEY_HOLE / 2 + 0.05
    prof = (cq.Workplane("YZ").polyline([(0, tab_top - TAB_T), (TAB_R, tab_top - TAB_T),
                                         (TAB_R, tab_top - (TAB_R - r0)), (r0, tab_top), (0, tab_top)]).close()
            .extrude(TAB_W / 2, both=True))
    # YZ workplane: local x = +Y (toward the back in case coordinates), so the tab points back
    k = k.union(prof.translate((X(x), Y(y), 0)))
    return k


PARTS = {"base": base, "lid": lid, "back": back, "front": front}


def build():
    parts = {name: f() for name, f in PARTS.items()}
    for ref, _ in BUTTONS:
        parts["button-" + ref] = button(ref)
    return parts


# how each part lies on the printer's bed: a rotation about X (degrees) from its fitted place
PRINT_ROT = {"base": 0, "lid": 180, "back": -90, "front": 90}


def for_print(name, shape):
    if name.startswith("button"):
        r = shape.rotate((0, 0, 0), (1, 0, 0), 180)   # head down: its top face is the first layer
    else:
        r = shape.rotate((0, 0, 0), (1, 0, 0), PRINT_ROT[name])
    bb = r.val().BoundingBox()
    return r.translate((-(bb.xmin + bb.xmax) / 2, -(bb.ymin + bb.ymax) / 2, -bb.zmin))


def main():
    out = os.path.join(HERE, "out")
    os.makedirs(out, exist_ok=True)
    parts = build()
    asm = cq.Assembly()
    for name, shape in parts.items():
        cq.exporters.export(shape, os.path.join(out, name + "-fitted.stl"), tolerance=0.02, angularTolerance=0.1)
        if not name.startswith("button") or name == "button-SW1":
            pname = "button" if name.startswith("button") else name
            cq.exporters.export(for_print(name, shape), os.path.join(out, pname + ".stl"),
                                tolerance=0.02, angularTolerance=0.1)
        asm.add(shape, name=name)
    asm.save(os.path.join(out, "case.step"))
    import json
    with open(os.path.join(out, "meta.json"), "w") as f:
        json.dump({"CX": CX, "CY": CY, "Z_BOT": Z_BOT, "Z_TOP": Z_TOP, "Z_LID": Z_LID,
                   "fan": [X(FAN_AT[0]), Y(FAN_AT[1]), FAN, Z_LID - FAN_T]}, f)
    print("outside %.1f x %.1f x %.1f mm" % (X_OUT1 - X_OUT0, Y_OUT1 - Y_OUT0, Z_TOP - Z_BOT))
    for name, shape in parts.items():
        bb = shape.val().BoundingBox()
        print("%-12s %6.1f x %6.1f x %6.1f  %6.1f cm3" % (name, bb.xlen, bb.ylen, bb.zlen, shape.val().Volume() / 1000))


if __name__ == "__main__":
    main()
