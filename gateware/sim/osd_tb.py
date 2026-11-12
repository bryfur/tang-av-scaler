#!/usr/bin/env python3
"""osd_tb.py: rtl/osd.v (iverilog): a frame of a picture through it with some text written, every
pixel and its timing against what the font and the text say."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
X0, Y0, COLS, ROWS, PAD, LAT = 40, 6, 12, 2, 4, 7
HA, HT, VA, VT = 280, 300, 90, 96
TEXT = ["Ag 59.94Hz %", "\x7fC ~|{}@#W_j"]


def pic(x, y):
    return (x * 7 + y * 3) & 255, (x + y * 5) & 255, (x * 3 ^ y) & 255


def main():
    os.makedirs(WORK, exist_ok=True)
    font = [int(t, 16) for t in open(os.path.join(HERE, "../rtl/osd_font.hex"))]
    writes = [(r * 64 + c, ord(ch)) for r, line in enumerate(TEXT) for c, ch in enumerate(line)]
    tb = '''`timescale 1ns/1ps
module tb;
    reg clk = 0; always #1 clk = ~clk;
    reg wclk = 0; always #3.1 wclk = ~wclk;
    reg [5:0] t = 0; reg [23:0] rgb = 0; reg on = 0, we = 0; reg [8:0] wa; reg [7:0] wd;
    wire [5:0] o_t; wire [23:0] o_rgb;
    osd #(.X0(%d), .Y0(%d), .COLS(%d), .ROWS(%d), .PAD(%d)) dut (.clk(clk), .on(on), .i_t(t), .i_rgb(rgb), .o_t(o_t),
        .o_rgb(o_rgb), .wclk(wclk), .we(we), .wa(wa), .wd(wd));
    integer f, x, y, k, fr;
    reg [16:0] wr [0:%d];
    initial begin
        $readmemh("%s/osd_wr.hex", wr);
        for (k = 0; k < 512; k = k + 1) begin @(posedge wclk); we <= 1; wa <= k; wd <= 8'd0; end
        for (k = 0; k <= %d; k = k + 1) begin @(posedge wclk); we <= 1; wa <= wr[k][16:8]; wd <= wr[k][7:0]; end
        @(posedge wclk); we <= 0; on <= 1;
        f = $fopen("%s/osd_out.bin", "wb");
        for (fr = 0; fr < 2; fr = fr + 1)
            for (y = 0; y < %d; y = y + 1)
                for (x = 0; x < %d; x = x + 1) begin
                    @(posedge clk);
                    t <= {x < %d && y < %d, x >= %d && x < %d, y >= %d, 3'd0};
                    rgb <= {x[7:0] * 8'd7 + y[7:0] * 8'd3, x[7:0] + y[7:0] * 8'd5, (x[7:0] * 8'd3) ^ y[7:0]};
                    #0.1;
                    if (fr == 1) $fwrite(f, "%%c%%c%%c%%c", 8'd64 + {2'd0, o_t}, o_rgb[23:16], o_rgb[15:8], o_rgb[7:0]);
                end
        $fclose(f);
        $finish;
    end
endmodule
''' % (X0, Y0, COLS, ROWS, PAD, len(writes) - 1, WORK, len(writes) - 1, WORK, VT, HT, HA, VA, HA + 4, HA + 12, VA + 2)
    open(os.path.join(WORK, "osd_tb.v"), "w").write(tb)
    open(os.path.join(WORK, "osd_wr.hex"), "w").write("".join("%05x\n" % (a << 8 | c) for a, c in writes))
    subprocess.check_call(["iverilog", "-g2005", '-DOSD_FONT="%s"' % os.path.join(HERE, "../rtl/osd_font.hex"), "-o",
                           os.path.join(WORK, "osd.vvp"), os.path.join(WORK, "osd_tb.v"), os.path.join(HERE, "../rtl/osd.v")])
    subprocess.check_call(["vvp", os.path.join(WORK, "osd.vvp")], stdout=subprocess.DEVNULL)
    s = open(os.path.join(WORK, "osd_out.bin"), "rb").read()
    # (sample k of the second frame is the pixel LAT clocks before: the frame before's last ones first)
    bad = lit = 0
    n = HT * VT
    for k in range(n):
        src = (k - LAT) % n
        x, y = src % HT, src // HT
        de, hs, vs = x < HA and y < VA, HA + 4 <= x < HA + 12, y >= VA + 2
        want_t = de << 5 | hs << 4 | vs << 3
        r, g, b = pic(x, y)
        want = (r, g, b)
        if de and X0 - PAD <= x < X0 + 16 * COLS + PAD and Y0 - PAD <= y < Y0 + 32 * ROWS + PAD:
            want = (r >> 2, g >> 2, b >> 2)
            if X0 <= x < X0 + 16 * COLS and Y0 <= y < Y0 + 32 * ROWS:
                col, row = (x - X0) // 16, (y - Y0) // 32
                c = ord(TEXT[row][col]) if col < len(TEXT[row]) else 0
                if font[(c & 127) * 32 + (y - Y0) % 32] >> (15 - (x - X0) % 16) & 1:
                    want = (0xF0, 0xF0, 0xF0)
                    lit += 1
        got_t, got = s[4 * k] - 64, tuple(s[4 * k + 1:4 * k + 4])
        if got_t != want_t or (de and got != want):
            bad += 1
            if bad <= 5:
                print("  x %d y %d: got %02x %s want %02x %s" % (x, y, got_t, got, want_t, want))
    print("osd: %d of %d samples wrong (%d text pixels lit)" % (bad, n, lit))
    return 1 if bad or not lit else 0


if __name__ == "__main__":
    sys.exit(main())
