#!/usr/bin/env python3
"""tmds_tb.py: rtl/tmds.v against the standard's encoder, written out here as the DVI
specification's flow chart [DVI 1.0 Figure 3-5], for N = 1, 2 and 4 characters a clock (iverilog)."""
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOKENS = {0: 0b1101010100, 1: 0b0010101011, 2: 0b0101010100, 3: 0b1010101011}


def encode(stream):
    cnt, out = 0, []
    for d, c, de in stream:
        if not de:
            cnt = 0
            out.append(TOKENS[c])
            continue
        n1 = bin(d).count("1")
        xnor = n1 > 4 or (n1 == 4 and not d & 1)
        q = d & 1
        for i in range(1, 8):
            b = (q >> (i - 1) & 1) ^ (d >> i & 1)
            q |= (b ^ 1 if xnor else b) << i
        q |= (0 if xnor else 1) << 8
        n1 = bin(q & 255).count("1")
        n0 = 8 - n1
        q8 = q >> 8 & 1
        if cnt == 0 or n1 == n0:
            w = (q8 ^ 1) << 9 | q8 << 8 | (q & 255 if q8 else ~q & 255)
            cnt += (n1 - n0) if q8 else (n0 - n1)
        elif (cnt > 0 and n1 > n0) or (cnt < 0 and n0 > n1):
            w = 1 << 9 | q8 << 8 | (~q & 255)
            cnt += 2 * q8 + (n0 - n1)
        else:
            w = q8 << 8 | (q & 255)
            cnt += -2 * (q8 ^ 1) + (n1 - n0)
        out.append(w)
    return out


def run(n, stream):
    work = os.path.join(HERE, "build")
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, "in.hex"), "w") as f:
        for k in range(0, len(stream), n):
            v = 0
            for j in range(n):
                d, c, de = stream[k + j]
                v |= (d | c << 8 | de << 10) << 11 * j
            f.write("%x\n" % v)
    tb = '''`timescale 1ns/1ps
module tb;
    localparam N = %d, LEN = %d;
    reg clk = 0; always #1 clk = ~clk;
    reg [11 * N - 1:0] mem [0:LEN - 1];
    reg [8 * N - 1:0] d; reg [10 * N - 1:0] tok; reg [N - 1:0] de;
    wire [10 * N - 1:0] q;
    function [9:0] token(input [1:0] v);
        case (v)
            2'b00: token = 10'b1101010100;
            2'b01: token = 10'b0010101011;
            2'b10: token = 10'b0101010100;
            default: token = 10'b1010101011;
        endcase
    endfunction
    tmds_enc #(.N(N)) dut (.clk(clk), .d(d), .tok(tok), .de(de), .q(q));
    integer i, j;
    initial begin
        $readmemh("%s/in.hex", mem);
        for (i = 0; i < LEN + N + 3; i = i + 1) begin
            for (j = 0; j < N; j = j + 1) begin
                d[8 * j +: 8] = i < LEN ? mem[i][11 * j +: 8] : 8'd0;
                tok[10 * j +: 10] = token(i < LEN ? mem[i][11 * j + 8 +: 2] : 2'd0);
                de[j] = i < LEN ? mem[i][11 * j + 10] : 1'b0;
            end
            @(posedge clk); #0.1;
            if (i >= N + 3) $display("%%x", q);
        end
        $finish;
    end
endmodule
''' % (n, len(stream) // n, work)
    open(os.path.join(work, "tb.v"), "w").write(tb)
    subprocess.check_call(["iverilog", "-g2005", "-o", os.path.join(work, "tb.vvp"), os.path.join(work, "tb.v"),
                           os.path.join(HERE, "../rtl/tmds.v")])
    out = subprocess.check_output(["vvp", "-n", os.path.join(work, "tb.vvp")], text=True).splitlines()
    got = []
    for line in out:
        if not line or any(ch not in "0123456789abcdefxz" for ch in line):
            continue                                    # $finish's own line
        v = int(line.replace("x", "0").replace("z", "0"), 16)
        got += [v >> 10 * j & 1023 for j in range(n)]
    return got


def main():
    random.seed(1)
    stream = []
    for _ in range(300):                                 # lines: blanking with syncs, then pixels of several kinds
        stream += [(0, random.randrange(4), 0)] * random.randrange(2, 9)
        kind = random.randrange(4)
        for _ in range(random.randrange(1, 60)):
            stream.append(({0: random.randrange(256), 1: random.choice((0, 255, 191)), 2: random.choice((0x55, 0xAA, 0x0F)),
                            3: random.choice((1, 2, 254, 127, 128))}[kind], 0, 1))
    stream += [(0, 0, 0)] * (-len(stream) % 4)
    want = encode(stream)
    bad = 0
    for n in (1, 2, 4):
        got = run(n, stream)
        errs = [k for k in range(len(want)) if k >= len(got) or got[k] != want[k]]
        print("N = %d: %d characters, %d wrong%s" % (n, len(want), len(errs),
              "" if not errs else " (first at %d: got %03x, want %03x)" % (errs[0], got[errs[0]] if errs[0] < len(got) else -1, want[errs[0]])))
        bad += len(errs)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
