#!/usr/bin/env python3
"""scr_tb.py: rtl/hdmi_scr.v (iverilog):
  1. its LFSR against the values published for HDMI 2.0's (US 11,962,847 FIG. 2: the seed and the
     21 values after it, each channel): read back as the mask on bytes of zero after the eight
     unscrambled characters, low byte (opt 0) and high byte (opt 1);
  2. every output against a model written from the same sources (the framing, the control codes,
     the toggle), for 1 and 4 characters a clock, every channel and every opt."""
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIG2 = {0: "FFFF 77EB 4B7C A445 DDBD EDCE FEFA 4AEA 0A44 CC0B ABDC 14B3 9B17 BF87 67A4 CC6F CFDC 34DF 5F30 C052 EAD1 49FD",
        1: "FFFE 76EB 737D 3D78 3838 A03D 45B9 094A 8A08 5095 355C E431 C1F2 72D0 A879 F9B0 A8ED 6DB0 5064 C45C 04D5 3504",
        2: "FFFD 75EB 3B7E AE3E 2EB6 7628 B07D CDAA 32DD CD36 AEDD CDB6 2EDD 1D28 C01F A7D1 01BE 8601 4198 C84E 0ED8 B00F"}
FIG2 = {k: [int(x, 16) for x in v.split()] for k, v in FIG2.items()}
TOKEN = {0: 0b1101010100, 1: 0b0010101011, 2: 0b0101010100, 3: 0b1010101011}
CODES = [0b0000010111, 0b0000011011, 0b0000011101, 0b0000011110, 0b0000100111, 0b0000110011, 0b0000111001,
         0b0000111100, 0b0001000111, 0b0001100011, 0b0001110001, 0b0001111000, 0b0010000111, 0b0011000011,
         0b0011100001, 0b0011110000]


def step8(v):
    for _ in range(8):
        v = (v << 1 & 0xFFFF) ^ (0x3801 if v >> 15 else 0)
    return v


def rev8(v):
    return int(format(v, "08b")[::-1], 2)


def model(stream, n, ch, frame, scramble, opt):
    """stream: (d, c, de, gb, ucc) a character -> (d_o, de_o, tok) a character."""
    seed, lfsr, tog, out = 0xFFFF - ch, 0xFFFF - ch, 0, []
    for w in range(0, len(stream), n):
        word = stream[w:w + n]
        v = lfsr
        for d, c, de, gb, ucc in word:
            mask = [v & 255, v >> 8, rev8(v & 255), rev8(v >> 8)][opt & 3]
            cv = (ch << 2 | c) if opt & 8 else (c << 2 | ch)
            cm = (v >> 11 & 15) if opt & 4 else int(format(v >> 11 & 15, "04b")[::-1], 2)
            is_data = bool(de or (frame and gb))
            byte = (d if de else (0x55 if ch == 1 else 0xAB)) ^ (mask if scramble else 0)
            if not scramble or ucc:
                tok = TOKEN[c]
                tog = 0
            else:
                e = CODES[cv ^ cm]
                tok = e ^ 0x3FF if tog else e
                if not is_data:
                    tog ^= 1
            out.append((byte, int(is_data), tok))
            v = step8(v)
        lfsr = seed if word[-1][4] else v
    return out


def run(stream, n, ch, frame, scramble, opt, tag):
    work = os.path.join(HERE, "build")
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, "scr.hex"), "w") as f:
        for k in range(0, len(stream), n):
            v = 0
            for j in range(n):
                d, c, de, gb, ucc = stream[k + j]
                v |= (d | c << 8 | de << 10 | gb << 11 | ucc << 12) << 13 * j
            f.write("%x\n" % v)
    tb = '''`timescale 1ns/1ps
module tb;
    localparam N = %d, LEN = %d;
    reg clk = 0; always #1 clk = ~clk;
    reg [13 * N - 1:0] mem [0:LEN - 1];
    reg [8 * N - 1:0] d; reg [2 * N - 1:0] c; reg [N - 1:0] de, gb, ucc;
    wire [8 * N - 1:0] d_o; wire [N - 1:0] de_o; wire [10 * N - 1:0] tok;
    hdmi_scr #(.N(N), .CH(%d)) dut (.clk(clk), .ce(1'b1), .frame(1'b%d), .scramble(1'b%d), .opt(4'd%d), .d(d), .c(c), .de(de),
                                    .gb(gb), .ucc(ucc), .d_o(d_o), .de_o(de_o), .tok(tok));
    integer i, j;
    initial begin
        $readmemh("%s/scr.hex", mem);
        d = 0; c = 0; de = 0; gb = 0; ucc = 0;
        repeat (3) @(posedge clk);
        #0.1;
        for (i = 0; i < LEN + 1; i = i + 1) begin
            for (j = 0; j < N; j = j + 1) begin
                d[8 * j +: 8] = i < LEN ? mem[i][13 * j +: 8] : 8'd0;
                c[2 * j +: 2] = i < LEN ? mem[i][13 * j + 8 +: 2] : 2'd0;
                de[j] = i < LEN ? mem[i][13 * j + 10] : 1'b0;
                gb[j] = i < LEN ? mem[i][13 * j + 11] : 1'b0;
                ucc[j] = i < LEN ? mem[i][13 * j + 12] : 1'b0;
            end
            @(posedge clk); #0.1;
            if (i >= 1) $display("%%x %%x %%x", d_o, de_o, tok);
        end
        $finish;
    end
endmodule
''' % (n, len(stream) // n, ch, frame, scramble, opt, work)
    open(os.path.join(work, "scr_tb.v"), "w").write(tb)
    subprocess.check_call(["iverilog", "-g2005", "-o", os.path.join(work, "scr.vvp"), os.path.join(work, "scr_tb.v"),
                           os.path.join(HERE, "../rtl/hdmi_scr.v")])
    got = []
    for line in subprocess.check_output(["vvp", "-n", os.path.join(work, "scr.vvp")], text=True).splitlines():
        p = line.split()
        if len(p) != 3 or any(ch_ not in "0123456789abcdef" for ch_ in "".join(p)):
            if len(p) == 3:
                sys.exit("%s: unknowns in the output: %s" % (tag, line))
            continue
        dv, ev, tv = (int(x, 16) for x in p)
        got += [(dv >> 8 * j & 255, ev >> j & 1, tv >> 10 * j & 1023) for j in range(n)]
    return got


def main():
    bad = 0
    # 1. the LFSR: eight unscrambled characters, then bytes of zero
    for n in (1, 4):
        for ch in (0, 1, 2):
            stream = [(0, 0, 0, 0, 0)] * 8 + [(0, 0, 0, 0, 1)] * 8 + [(0, 0, 1, 0, 0)] * 24
            lo = run(stream, n, ch, 1, 1, 0, "lfsr")
            hi = run(stream, n, ch, 1, 1, 1, "lfsr")
            seen = [hi[k][0] << 8 | lo[k][0] for k in range(16, 16 + 22)]
            ok = seen == FIG2[ch]
            bad += not ok
            print("LFSR, channel %d, %d a clock: %s%s" % (ch, n, " ".join("%04X" % v for v in seen[:6]),
                                                          " ... as published" if ok else " ... NOT the published values"))
    # 2. everything, against the model
    random.seed(2)
    stream = []
    for line in range(40):
        blank = random.randrange(5, 12) * 4
        for k in range(blank):
            pre_gb = line % 3 != 2
            stream.append((0, random.randrange(4) if k % 7 == 0 else 1, 0, int(pre_gb and k >= blank - 2),
                           int(line % 5 == 0 and 8 <= k < 16)))
        if line % 3 != 2:
            stream += [(random.randrange(256), 0, 1, 0, 0) for _ in range(random.randrange(1, 9) * 4)]
    cases = wrong = 0
    for n in (1, 4):
        for ch in (0, 1, 2):
            for frame, scramble, opt in [(0, 0, 0), (1, 0, 0)] + [(1, 1, o) for o in range(16)] + [(0, 1, 5)]:
                got = run(stream, n, ch, frame, scramble, opt, "model")
                want = model(stream, n, ch, frame, scramble, opt)
                # (from the first unscrambled characters on: before them the LFSR is wherever it was)
                errs = [k for k in range(16 if scramble else 0, len(want)) if k >= len(got) or got[k] != want[k]]
                cases += 1
                if errs:
                    wrong += 1
                    if wrong < 4:
                        k = errs[0]
                        print("  n %d ch %d frame %d scramble %d opt %d: %d differ, first at %d: got %s want %s" % (
                            n, ch, frame, scramble, opt, len(errs), k, got[k] if k < len(got) else None, want[k]))
    print("against the model: %d cases of %d characters, %d with differences" % (cases, len(stream), wrong))
    sys.exit(1 if bad or wrong else 0)


if __name__ == "__main__":
    main()
