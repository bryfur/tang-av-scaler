#!/usr/bin/env python3
"""The Tang Mega 138K SOM's board-to-board pinout, read from the Tang Console's schematic
(refs/console138k_C.pdf, sheets SOM_BTB0-2, pages 4-6) into rev-c/som-pinout.csv:

    connector, pin, net, console_use, clock

connector: the Console's reference (J0 the 80-pin, J1 and J2 the 100-pin connectors); net: the
label on the pin's wire (BANKb_BALL_IOname, GND, VBUS_SOM, VCCO_n, Q0_..., DONE, READY); console_use:
what the Console wires there (for reference only); clock: the ball's clock functions, from the
"BALL:FUNCTION" notes on the same pages.

Needs PyMuPDF (~/tools/eda-venv):  ~/tools/eda-venv/bin/python rev-c/som_pinout.py
"""
import csv
import os
import re

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(os.path.dirname(HERE), "refs", "console138k_C.pdf")
PAGES = ((3, "J0", 80), (4, "J1", 100), (5, "J2", 100))
LABEL = re.compile(r"^(BANK\d|GND|VCC|VBUS|Q\d_|DONE|READY|ADC_)")
# J2's lower odd pins carry no label on their wires (drawn as a ground bus and a VBUS_SOM bus, and
# VCCO_5 off to the left): read off the sheet by eye
J2_BY_EYE = {67: "VCCO_5", 77: "GND", 79: "GND", 81: "GND", 83: "GND", 85: "GND", 87: "GND",
             89: "VBUS_SOM", 91: "VBUS_SOM", 93: "VBUS_SOM", 95: "VBUS_SOM", 97: "VBUS_SOM", 99: "VBUS_SOM"}


def centre_y(w):
    return (w[1] + w[3]) / 2


def main():
    d = pymupdf.open(PDF)
    clocks = {}
    for page, _, _ in PAGES:
        for w in d[page].get_text("words"):
            m = re.match(r"^([A-Z]{1,2}\d{1,2}):(\S+)$", w[4])
            if m:
                clocks.setdefault(m.group(1), set()).add(m.group(2))
    rows = []
    for page, ref, count in PAGES:
        words = d[page].get_text("words")
        body = [w for w in words if w[4].startswith("DF40HC")][0]
        cx = (body[0] + body[2]) / 2
        # the symbol's pin numbers (each drawn twice, outside and inside the body), within its width
        nums = [w for w in words if re.fullmatch(r"\d{1,3}", w[4]) and w[1] > body[3]
                and body[0] - 20 < w[0] < body[2] + 20 and 1 <= int(w[4]) <= count]
        net, names = {}, {}
        for n in nums:
            pin, yc, left = int(n[4]), centre_y(n), n[0] < cx
            side = [w for w in words if abs(centre_y(w) - yc) < 2.0 and not re.fullmatch(r"\d{1,3}", w[4])
                    and ((w[2] < n[0]) if left else (w[0] > n[2]))]
            side.sort(key=lambda w: abs((w[0] + w[2]) / 2 - (n[0] + n[2]) / 2))
            labels = [w for w in side if LABEL.match(w[4])]
            if labels and pin not in net and abs((labels[0][0] + labels[0][2]) / 2 - (n[0] + n[2]) / 2) < 120:
                net[pin] = labels[0][4]
            for w in side[:5]:
                if re.fullmatch(r"[A-Za-z{][\w.{}~#+/-]{2,}", w[4]) and not LABEL.match(w[4]) \
                        and not re.match(r"^[A-Z]{1,2}\d{1,2}:", w[4]) and w[4] not in names.setdefault(pin, []):
                    names[pin].append(w[4])
        if ref == "J2":
            net.update(J2_BY_EYE)
        missing = [p for p in range(1, count + 1) if p not in net]
        assert not missing, (ref, missing)
        for pin in range(1, count + 1):
            ball = net[pin].split("_")[1] if net[pin].startswith("BANK") else None
            use = [s for s in names.get(pin, []) if not s.startswith(("Note", "BANK"))]
            rows.append((ref, pin, net[pin], " ".join(use[:2]), " ".join(sorted(clocks.get(ball, ())))))
    with open(os.path.join(HERE, "som-pinout.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("connector", "pin", "net", "console_use", "clock"))
        w.writerows(rows)
    print("%d pins" % len(rows))


if __name__ == "__main__":
    main()
