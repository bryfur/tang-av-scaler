"""The Tang Mega 138K SOM on a rev C carrier: its three board-to-board receptacles, its four
standoffs, and its pinout (som-pinout.csv, from the Console's schematic: som_pinout.py).

Geometry, all copied from the Tang Console (refs/ibom_C.html, its interactive BOM): relative to the
centre of the SOM's four M2 holes (41 x 31 mm apart, 45 x 35 mm module),

    J1 (100-pin)  (+6.500, -14.7375), 180 deg      J0 (80-pin)  (+19.885, -0.0375), 90 deg
    J2 (100-pin)  (+6.500, +14.6625), 180 deg      holes        (+-20.5, +-15.4975)

The receptacles are Hirose DF40HC(3.0)-100DS-0.4V(51) and -80DS (3.0 mm stack, the standoffs'
height). Their numbering is the Console's (and Hirose's): pin 2k-1 and pin 2k face each other
across the two rows, pin 1 at one end. EasyEDA's footprints number one row 1-50 and the other
51-100, which would put nearly every SOM pin on the wrong signal: write_footprints() makes
DF40HC-*-SOM footprints from EasyEDA's outline with the Console's pads (check_som_fp.py compares
them with the Console's iBOM).
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIB = os.path.join(ROOT, "lib", "lcsc.pretty")

# The connectors: our reference, the Console's, pin count, offset from the holes' centre, angle
CONNECTORS = {"J21": ("J1", 100, (6.5, -14.7375), 180),
              "J22": ("J2", 100, (6.5, 14.6625), 180),
              "J20": ("J0", 80, (19.885, -0.0375), 90)}
HOLES = [(sx * 20.5, sy * 15.4975) for sy in (-1, 1) for sx in (-1, 1)]
SIZE = (45.0, 35.0)
FOOTPRINT = {100: "DF40HC-3.0-100DS-SOM", 80: "DF40HC-3.0-80DS-SOM"}
# the courtyard: the Console's footprint outline (its iBOM: 24.65 / 20.65 x 5.83 mm), 0.4 mm short of
# it at each end (the receptacle's body: (n/2 - 1) x 0.4 mm of pins plus about 3.4 mm)
COURTYARD = {100: (24.65 - 0.8, 5.83), 80: (20.65 - 0.8, 5.83)}
# The SOM's four M2 holes: the Console's (2.2 mm plated, a 3.8 mm ring on both sides, to GND), for
# M2 x 3 mm brass spacers fitted by hand (JLCPCB's only M2 x 3 mm SMD nut has a 5.6 mm flange, which
# would sit on the receptacles' ends) and M2 screws from below. Courtyard: the spacer, 3.7 mm across
HOLE_FOOTPRINT = "SOM-M2-Hole"
EASYEDA = {100: "CONN-SMD_DF40HC-3.0-100DS-0.4V-51", 80: "CONN-SMD_DF40HC-3.0-80DS-0.4V-51"}
LCSC = {100: "C424649", 80: "C2858577"}
SYMBOL = {100: "lcsc:DF40HC", 80: "lcsc:DF40HC-80DS"}


def pad_xy(n, count):
    """Pin n's pad in the footprint's own frame (as on the Console, before its rotation)."""
    k = (n + 1) // 2
    x = -(count / 4 - 0.5) * 0.4 + (k - 1) * 0.4
    return round(x, 3), (1.54 if n % 2 else -1.54)


def pins():
    """{our connector ref: {pin: (net, console_use, clock)}}"""
    by_console = {v[0]: k for k, v in CONNECTORS.items()}
    out = {k: {} for k in CONNECTORS}
    with open(os.path.join(HERE, "som-pinout.csv")) as f:
        for row in csv.DictReader(f):
            out[by_console[row["connector"]]][int(row["pin"])] = (row["net"], row["console_use"], row["clock"])
    return out


def ball(net):
    """'BANK2_E19_IOR29A' -> ('2', 'E19'); None for supplies and the like."""
    if not net.startswith("BANK"):
        return None
    b, ball_, _ = net.split("_", 2)
    return b[4:], ball_


def write_footprints():
    """DF40HC-*-SOM.kicad_mod: EasyEDA's outline and model, the Console's pads and numbering."""
    import re
    for count, name in FOOTPRINT.items():
        src = open(os.path.join(LIB, EASYEDA[count] + ".kicad_mod")).read()
        # drop EasyEDA's pads (one per line or spanning several: up to the closing paren at depth 1)
        out, i = [], 0
        while True:
            j = src.find("(pad ", i)
            if j < 0:
                out.append(src[i:])
                break
            out.append(src[i:j])
            depth, k = 0, j
            while True:
                if src[k] == "(":
                    depth += 1
                elif src[k] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            i = k + 1
        body = "".join(out)
        body = re.sub(r'\(footprint "[^"]+"', '(footprint "%s"' % name, body, count=1)
        # the courtyard: EasyEDA's lines on F.CrtYd dropped, a rectangle round the body instead
        body = re.sub(r'\(fp_(?:line|rect|poly|circle|arc)\b(?:[^()]|\((?:[^()]|\([^()]*\))*\))*?\(layer "F\.CrtYd"\)'
                      r'(?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)', "", body)
        w, h = COURTYARD[count]
        crt = '\n\t(fp_rect (start %.3f %.3f) (end %.3f %.3f) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))' \
            % (-w / 2, -h / 2, w / 2, h / 2)
        pads = "".join('\n\t(pad "%d" smd rect (at %.3f %.3f) (size 0.2 0.7) (layers "F.Cu" "F.Paste" "F.Mask"))'
                       % ((n,) + pad_xy(n, count)) for n in range(1, count + 1))
        k = body.rstrip().rfind(")")
        open(os.path.join(LIB, name + ".kicad_mod"), "w").write(body[:k].rstrip() + crt + pads + "\n)\n")
        print(os.path.join(LIB, name + ".kicad_mod"))
    hole = """(footprint "%s"
\t(version 20241229)
\t(generator "rev-c/som.py")
\t(layer "F.Cu")
\t(descr "The SOM's M2 hole (as the Tang Console's): 2.2 mm plated, 3.8 mm ring both sides")
\t(property "Reference" "REF**" (at 0 -3 0) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.15))))
\t(property "Value" "M2" (at 0 3 0) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.15))))
\t(attr exclude_from_pos_files exclude_from_bom)
\t(fp_circle (center 0 0) (end 1.85 0) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))
\t(fp_circle (center 0 0) (end 1.85 0) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
\t(pad "1" thru_hole circle (at 0 0) (size 3.8 3.8) (drill 2.2) (layers "*.Cu" "*.Mask"))
)
""" % HOLE_FOOTPRINT
    open(os.path.join(LIB, HOLE_FOOTPRINT + ".kicad_mod"), "w").write(hole)
    print(os.path.join(LIB, HOLE_FOOTPRINT + ".kicad_mod"))


if __name__ == "__main__":
    write_footprints()
