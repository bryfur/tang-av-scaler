#!/usr/bin/env python3
"""still.py [OUTDIR] [--again] [--at X,Y ...]: stills for comparing what comes in with what goes out, of one frozen frame:

    in_480i_720x480.png     the two newest fields as the console sent them (the capture's samples,
                            read out of the DDR3), woven into one frame, nothing else done
    in_basic_1920x1080.png  the part of it the scaler shows, made 1080p the plain way (the two fields
                            woven, stretched bilinear): what a simple scaler or a display would show
    out_1920x1080.png       the scaler's picture: every pixel as it leaves for the display (read back
                            from the FPGA: no camera, no capture device in between)
    split_1920x1080.png     the left half of the plain one beside the right half of the scaler's
    compare_N.png           parts of the last two side by side, enlarged

--again: only the comparisons, from the stills already in OUTDIR.  --at X,Y (as often as wanted):
the parts compared are the 320 x 180 ones with these top left corners in the 1080p picture (else
the four with most detail).

The link (AV_HOST, default avscaler.local) freezes the picture and reads the output back; the fields
come through the monitor (AVB_TTY, default the link's console port).  The on-screen text is off
meanwhile.  Best on a still scene (a pause menu): the two fields are 1/60 s apart."""
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image

HOST = os.environ.get("AV_HOST", "avscaler.local")
os.environ.setdefault("AVB_TTY", "tcp:%s:2323" % HOST)
import avb

DDR, DDRD, DSTAT = 0x40, 0x48, 0x36


def api(**kw):
    url = "http://%s/api/video" % HOST
    data = urllib.parse.urlencode(kw).encode() if kw else None
    r = urllib.request.urlopen(url, data, timeout=10).read()
    return None if kw else json.loads(r)


def field(m, slot, lines=240):
    """a field's lines out of the DDR3: each 360 words (cb, y0, cr, y1).  A line of the memory is
    asked for, then (a read of the state first: the memory's answer takes longer than the monitor
    does between two commands that are both waiting) its eight words read; two lines of picture a
    round trip"""
    out = []
    for n0 in range(0, lines, 2):
        todo = range(n0, min(n0 + 2, lines))
        want = len(todo) * 45 * 36
        for attempt in range(10):
            for n in todo:
                for c in range(45):
                    m.out += b"W" + bytes([DDR]) + (slot << 22 | n << 7 | c).to_bytes(4, "little")
                    m.out += bytes([ord("R"), DDR]) + b"".join(bytes([ord("R"), DDRD + k]) for k in range(8))
            m.flush()
            buf, t = b"", time.time()
            while len(buf) < want and time.time() - t < 1.5:
                buf += m.read_raw()
                time.sleep(0.001)
            if len(buf) == want:
                break
            # a byte was lost on the way (the link is a radio): the monitor drops a command cut
            # short after 40 ms of silence, the picture is frozen, so the lines are asked for again
            quiet = time.time()
            while time.time() - quiet < 0.3:
                if m.read_raw():
                    quiet = time.time()
                time.sleep(0.005)
        else:
            sys.exit("still: the monitor stopped answering (field line %d)" % n0)
        for i in range(len(todo)):
            words = [int.from_bytes(buf[36 * (45 * i + c) + 4 + 4 * k:][:4], "little") for c in range(45) for k in range(8)]
            out.append([(w >> 24, w >> 16 & 255, w >> 8 & 255, w & 255) for w in words])
    return out


def rgb(y, cb, cr):
    """BT.601, 16-235, as rtl/rcas.v does it"""
    clamp = lambda v: 0 if v < 0 else 255 if v > 0xFFFF else v >> 8
    yy = 298 * max(y - 16, 0)
    return (clamp(yy + 409 * (cr - 128) + 128), clamp(yy - 100 * (cb - 128) - 208 * (cr - 128) + 128),
            clamp(yy + 516 * (cb - 128) + 128))


def line_rgb(words):
    """a line's 720 pixels: an even pixel has its word's chroma, an odd one the mean with the next word's"""
    px = []
    for q, (cb, y0, cr, y1) in enumerate(words):
        nb, nr = (words[q + 1][0], words[q + 1][2]) if q + 1 < len(words) else (cb, cr)
        px.append(rgb(y0, cb, cr))
        px.append(rgb(y1, (cb + nb + 1) >> 1, (cr + nr + 1) >> 1))
    return px


def main():
    at = [tuple(int(t) for t in v.split(",")) for k, v in enumerate(sys.argv[1:]) if k and sys.argv[k] == "--at"]
    a = [v for k, v in enumerate(sys.argv[1:]) if not v.startswith("--") and (k == 0 or sys.argv[k] != "--at")]
    out = a[0] if a else "stills"
    os.makedirs(out, exist_ok=True)
    if "--again" in sys.argv:           # the comparisons made again from the stills that are there
        basic, ours = (Image.open(os.path.join(out, n)).convert("RGB") for n in ("in_basic_1920x1080.png", "out_1920x1080.png"))
        compare(out, basic, ours, basic.getpixel((100, 540)) != (0, 0, 0) or ours.getpixel((100, 540)) != (0, 0, 0), at)
        return
    was = api()["set"]
    api(osd=0, freeze=1)
    time.sleep(1.5)
    try:
        st = api()
        x0, w, y0, h = st["shown"]
        wide = st["set"]["wide"]
        print("frozen; the part shown: %d x %d from %d, %d, %s" % (w, h, x0, y0, "16:9" if wide else "4:3"))
        t = time.time()
        bmp = urllib.request.urlopen("http://%s/api/grab?step=1" % HOST, timeout=300).read()
        ours = Image.open(io.BytesIO(bmp)).convert("RGB")
        ours.save(os.path.join(out, "out_1920x1080.png"))
        print("out_1920x1080.png (%.0f s)" % (time.time() - t))
        t = time.time()
        m = avb.Mon()
        d = m.r(DSTAT)
        latest, pc = d >> 3 & 7, d >> 13 & 1
        c, p1 = field(m, latest), field(m, (latest - 1) & 7)
        del m
        print("the fields in slots %d and %d read (%.0f s)" % (latest, (latest - 1) & 7, time.time() - t))
    finally:
        time.sleep(1.5)
        api(osd=was["osd"], freeze=was["freeze"])
    # woven: the newest field's lines on the frame's odd lines if pc (rtl/deint.v), else on the even ones
    frame = Image.new("RGB", (720, 480))
    for k in range(240):
        for f, par in ((c, pc), (p1, 1 - pc)):
            row = Image.new("RGB", (720, 1))
            row.putdata(line_rgb(f[k]))
            frame.paste(row, (0, 2 * k + par))
    frame.save(os.path.join(out, "in_480i_720x480.png"))
    ow = 1920 if wide else 1440
    basic = Image.new("RGB", (1920, 1080))
    basic.paste(frame.crop((x0, y0, x0 + w, y0 + h)).resize((ow, 1080), Image.BILINEAR), ((1920 - ow) // 2, 0))
    basic.save(os.path.join(out, "in_basic_1920x1080.png"))
    compare(out, basic, ours, wide, at)
    print("%s: in_480i_720x480.png, in_basic_1920x1080.png, out_1920x1080.png, split_1920x1080.png, compare_1..4.png" % out)


def label(im, xy, text):
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(im)
    w = d.textlength(text, font=font)
    d.rectangle((xy[0], xy[1], xy[0] + w + 16, xy[1] + 34), fill=(0, 0, 0))
    d.text((xy[0] + 8, xy[1] + 4), text, font=font, fill=(255, 255, 255))


def compare(out, basic, ours, wide, at=()):
    """the plain picture and the scaler's: the frame's left half of the one beside the right half of
    the other; and parts of both, three times the size, side by side: where the picture has most detail"""
    A, B = "480i in: fields woven, stretched", "1080p out: the scaler"
    split = basic.copy()
    split.paste(ours.crop((960, 0, 1920, 1080)), (960, 0))
    split.paste(Image.new("RGB", (2, 1080), (255, 255, 255)), (959, 0))
    label(split, (20, 1030), A)
    label(split, (980, 1030), B)
    split.save(os.path.join(out, "split_1920x1080.png"))
    g = ours.convert("L").resize((48, 27))
    cells = sorted(((abs(g.getpixel((x, y)) - g.getpixel((x + 1, y))) + abs(g.getpixel((x, y)) - g.getpixel((x, y + 1))), x, y)
                    for y in range(2, 24, 4) for x in range(8 if not wide else 2, 40 if not wide else 46, 6)), reverse=True)
    # (or the parts named: --at X,Y their top left corners in the 1920 x 1080 picture)
    corners = list(at) or [(cx * 40 - 140, cy * 40 - 90) for _, cx, cy in cells[:4]]
    for n, (bx, by) in enumerate(corners):
        bx, by = min(max(bx, 0), 1920 - 320), min(max(by, 0), 1080 - 180)
        box = (bx, by, bx + 320, by + 180)
        cmp_ = Image.new("RGB", (2 * 960 + 20, 540), "white")
        cmp_.paste(basic.crop(box).resize((960, 540), Image.NEAREST), (0, 0))
        cmp_.paste(ours.crop(box).resize((960, 540), Image.NEAREST), (980, 0))
        label(cmp_, (12, 496), A + " (3x)")
        label(cmp_, (992, 496), B + " (3x)")
        cmp_.save(os.path.join(out, "compare_%d.png" % (n + 1)))


if __name__ == "__main__":
    main()
