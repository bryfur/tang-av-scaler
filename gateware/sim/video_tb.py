#!/usr/bin/env python3
"""video_tb.py: the component input's path (iverilog): a BT.656 field into rtl/vcap.v and the frame
store (fbram.v), then a 1080p frame out of fbview.v beside pattern.v's timing, as rtl/top.v wires
them: every pixel of the frame against a model (the window, the scaling, Y'CbCr to RGB)."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
LAT, VOFF, LINES = 10, 2, 244


def src(line, x):
    """(Y, C) of the field's line and Y sample x: C is Cb for even x, Cr for odd"""
    y = 16 + (x * 7 + line * 3) % 220
    c = 16 + ((x >> 1) * 5 + line * 11 + (x & 1) * 97) % 225
    return y, c


def field(wide, f=0):
    """a 525-line field as the pixel port's samples (C pins << 8 | Y pins): 19 lines of blanking,
    LINES of picture, 4 of blanking; wide: 16 bits (Y and C side by side), else BT.656 on the Y pins"""
    out = []
    code = lambda xy: [b * 0x101 for b in (0xFF, 0, 0, xy)] if wide else [0xFF, 0, 0, xy]
    for n in range(19 + LINES + 4):
        v = 0 if 19 <= n < 19 + LINES else 1
        nxt = 0 if 19 <= n + 1 < 19 + LINES else 1
        out += code(0x80 | f << 6 | v << 5)                                  # SAV
        for x in range(720):
            y, c = src(n - 19, x) if not v else (0x10, 0x80)
            out += [c << 8 | y] if wide else [c, y]
        out += code(0x90 | f << 6 | nxt << 5)                                # EAV (V of the next line)
        out += [0x8010] * 130 if wide else [0x80, 0x10] * 134
    return out


def clamp(v):
    return 0 if v < 0 else 255 if v > 0xFFFF else v >> 8


def main():
    os.makedirs(WORK, exist_ok=True)
    wide = "wide" in sys.argv[1:]
    bottom = "bottom" in sys.argv[1:]            # the field is a bottom one (F = 1), shown as one
    data = field(wide, int(bottom))
    open(os.path.join(WORK, "vid_in.hex"), "w").write("\n".join("%04x" % b for b in data) + "\n")
    n_out = 2 * 2200 * 1125 + 2200 * 60
    tb = '''`timescale 1ns/1ps
module tb;
    reg llc = 0; always #18 llc = ~llc;
    reg clk = 0; always #3 clk = ~clk;
    reg [15:0] mem [0:%d];
    reg [15:0] y = 16'h8010;
    wire f_we, f_wd; wire [7:0] f_wa;
    wire fb_we; wire [16:0] fb_wa, fb_ra; wire [31:0] fb_wd, fb_rd;
    wire [10:0] pix; wire [9:0] lines; wire field; wire [15:0] fields; wire done; wire [18:0] raw_rd;
    vcap u_cap (.llc(llc), .y(y[7:0]), .c(y[15:8]), .hs(1'b0), .vs(1'b0), .de(1'b0), .freeze(1'b0), .wide(1'b%d), .we(fb_we), .wa(fb_wa), .f_we(f_we), .f_wa(f_wa), .f_wd(f_wd),
                .wd(fb_wd), .pix(pix), .lines(lines), .field(field), .fields(fields), .arm(1'b0), .mode(2'd0),
                .done(done), .rclk(clk), .ra(10'd0), .rd(raw_rd));
    wire de, hs, vs, pre, gb, ucc; wire [7:0] pr, pg, pb, r, g, b; wire [12:0] ox; wire [11:0] oy;
    pattern u_pat (.clk(clk), .de(de), .hs(hs), .vs(vs), .pre(pre), .gb(gb), .ucc(ucc), .r(pr), .g(pg), .b(pb),
                   .ox(ox), .oy(oy));
    fbram u_fb (.wclk(llc), .we(fb_we), .wa(fb_wa), .wd(fb_wd), .rclk(clk), .ra(fb_ra), .rd(fb_rd));
    fbview u_view (.clk(clk), .de(de), .x(ox), .y(oy), .base0(17'd%d), .voff(8'd%d), .swap(1'b0), .bob(1'b1), .top(1'b0), .f_clk(llc), .f_we(f_we), .f_wa(f_wa), .f_wd(f_wd), .ra(fb_ra), .rd(fb_rd), .r(r), .g(g), .b(b));
    reg [%d:0] dl = 0;
    always @(posedge clk) dl <= {dl, de};
    integer f, i;
    initial begin
        $readmemh("%s/vid_in.hex", mem);
        for (i = 0; i <= %d; i = i + 1) begin
            @(negedge llc); y = mem[i];
        end
        repeat (8) @(negedge llc);
        $display("pix %%0d lines %%0d fields %%0d", pix, lines, fields);
        f = $fopen("%s/vid_out.bin", "wb");
        for (i = 0; i < %d; i = i + 1) begin
            @(posedge clk); #0.1;
            $fwrite(f, "%%c%%c%%c%%c", 8'd65 + {7'd0, dl[%d]}, r, g, b);
        end
        $fclose(f);
        $finish;
    end
endmodule
''' % (len(data) - 1, wide, (VOFF * 360 - 60) % (1 << 17), VOFF, LAT - 1, WORK, len(data) - 1, WORK, n_out, LAT - 1)
    open(os.path.join(WORK, "vid_tb.v"), "w").write(tb)
    rtl = [os.path.join(HERE, "../rtl", f) for f in ("vcap.v", "fbram.v", "fbview.v", "pattern.v")]
    subprocess.check_call(["iverilog", "-g2005", "-o", os.path.join(WORK, "vid.vvp"), os.path.join(WORK, "vid_tb.v")] + rtl)
    print(subprocess.check_output(["vvp", "-n", os.path.join(WORK, "vid.vvp")]).decode().strip())
    s = open(os.path.join(WORK, "vid_out.bin"), "rb").read()
    de = [s[4 * k] - 65 for k in range(len(s) // 4)]
    # the first whole frame: the first de after a gap of more than a line
    k, gap, start = 0, 0, None
    while k < len(de):
        if de[k]:
            if gap > 3000:
                start = k
                break
            gap = 0
        else:
            gap += 1
        k += 1
    if start is None:
        sys.exit("no frame start found")
    bad = shown = 0
    for row in range(1080):
        for col in range(1920):
            k = start + row * 2200 + col
            got = tuple(s[4 * k + 1:4 * k + 4])
            if not de[k]:
                sys.exit("de low inside the picture at row %d col %d" % (row, col))
            if 240 <= col < 1680:
                sx = (col - 240) >> 1
                line = (max((8 * row - 5) // 36, 0) if bottom else min((8 * row + 13) // 36, 239)) + VOFF
                y = src(line, sx)[0]
                cb, cr = src(line, sx & ~1)[1], src(line, sx | 1)[1]
                yy = 298 * max(y - 16, 0)
                want = (clamp(yy + 409 * (cr - 128) + 128), clamp(yy - 100 * (cb - 128) - 208 * (cr - 128) + 128),
                        clamp(yy + 516 * (cb - 128) + 128))
            else:
                want = (0, 0, 0)
            if got != want:
                bad += 1
                if shown < 8:
                    shown += 1
                    print("  row %d col %d: got %s want %s" % (row, col, got, want))
    print("frame at clock %d: %d wrong pixels of %d" % (start, bad, 1080 * 1920))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
