#!/usr/bin/env python3
"""mkfont.py [OUT.hex]: the on-screen display's font (rtl/osd.v): the characters 32 to 126 of DejaVu
Sans Mono Bold (a free font: Bitstream Vera's licence), each 16 wide and 32 high, a bit a pixel; 127
a degree sign.  4096 words of 16 bits for $readmemh: [character * 32 + row], the left pixel the
highest bit.  rtl/osd_font.hex is this file's output, kept in the tree (a build needs no font)."""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H, SIZE = 16, 32, 26
TTF = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def glyphs():
    font = ImageFont.truetype(TTF, SIZE)
    asc, desc = font.getmetrics()
    top = (H - (asc + desc)) // 2
    out = []
    for c in range(128):
        ch = "°" if c == 127 else chr(c) if c >= 32 else " "
        im = Image.new("L", (W, H), 0)
        ImageDraw.Draw(im).text((0, top), ch, font=font, fill=255)
        px = im.load()
        out.append([sum(1 << (W - 1 - x) for x in range(W) if px[x, y] >= 112) for y in range(H)])
    return out


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "../rtl/osd_font.hex")
    g = glyphs()
    open(out, "w").write("".join("%04x\n" % r for ch in g for r in ch))
    for ch in "A9g%":
        print("\n".join("".join("#" if r >> (W - 1 - x) & 1 else "." for x in range(W)) for r in g[ord(ch)]))


if __name__ == "__main__":
    main()
