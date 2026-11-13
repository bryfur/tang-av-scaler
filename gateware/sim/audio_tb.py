#!/usr/bin/env python3
"""audio_tb.py: rtl/hdmi_audio.v beside rtl/pattern.v's timing for a frame and a bit (Verilator):
its characters decoded here (TERC4, the guard bands, the packets' error correction by polynomial
division, their contents): the InfoFrames' checksums, N and CTS, and every sample put in comes
out once, in order, with its parity and channel status."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
TERC4 = [0b1010011100, 0b1001100011, 0b1011100100, 0b1011100010, 0b0101110001, 0b0100011110, 0b0110001110,
         0b0100111100, 0b1011001100, 0b0100111001, 0b0110011100, 0b1011000110, 0b1010001110, 0b1001110001,
         0b0101100011, 0b1011000011]
GB = 0b0100110011
CS = bytes([0x04, 0x00, 0x00, 0x02, 0x0B])


def bch(bits):
    """the remainder of the bits (first sent first) times x^8 by 1 + x^6 + x^7 + x^8, as the eight
    bits sent after them (lowest first)"""
    reg = 0
    for b in bits:
        fb = (reg & 1) ^ b
        reg >>= 1
        if fb:
            reg ^= 0x83
    return reg


def main():
    os.makedirs(WORK, exist_ok=True)
    n = 2200 * 1125 + 2200 * 200
    tb = '''`timescale 1ns/1ps
module tb;
    reg clk = 0; always #3.37 clk = ~clk;
    reg aclk = 0; always #3.371 aclk = ~aclk;
    wire de, hs, vs, pre, gb, ucc; wire [7:0] r, g, b; wire [12:0] ox; wire [11:0] oy;
    pattern u_pat (.clk(clk), .de(de), .hs(hs), .vs(vs), .pre(pre), .gb(gb), .ucc(ucc), .r(r), .g(g), .b(b), .ox(ox), .oy(oy));
    // samples: a count in each, one every 3072 clocks of the sound's clock
    reg [23:0] sl = 24'h100000, sr = 24'hE00000; reg tick = 0; integer c = 0;
    always @(posedge aclk) begin
        c <= c == 3071 ? 0 : c + 1;
        if (c == 3071) begin sl <= sl + 24'd1; sr <= sr - 24'd3; tick <= !tick; end
    end
    wire a_pre, a_act; wire [9:0] k0, k1, k2;
    hdmi_audio u (.clk(clk), .en(1'b1), .hs(hs), .vs(vs), .cts_alt(1'b0), .s_tick(tick), .s_l(sl), .s_r(sr), .pre(a_pre), .act(a_act),
                  .k0(k0), .k1(k1), .k2(k2));
    integer f, i;
    initial begin
        f = $fopen("%s/audio_out.bin", "wb");
        for (i = 0; i < %d; i = i + 1) begin
            @(posedge clk); #0.1;
            $fwrite(f, "%%c%%c%%c%%c%%c", 8'd32 + {a_act, a_pre, de, vs, hs, k0[9:8], 1'b0}, k0[7:0], {k1[9:8], k2[9:8], 4'd0}, k1[7:0], k2[7:0]);
        end
        $fclose(f);
        $finish;
    end
endmodule
''' % (WORK, n)
    open(os.path.join(WORK, "audio_tb.v"), "w").write(tb)
    mdir = os.path.join(WORK, "vl_audio")
    subprocess.check_call(["verilator", "--binary", "--timing", "-j", "8", "-Wno-fatal", "-Wno-WIDTH", "-Wno-UNUSED",
                           "-Wno-DECLFILENAME", "-Wno-STMTDLY", "-Wno-INITIALDLY", "-Wno-TIMESCALEMOD", "--top-module", "tb",
                           "--Mdir", mdir, "-o", "audio", os.path.join(WORK, "audio_tb.v"),
                           os.path.join(HERE, "../rtl/hdmi_audio.v"), os.path.join(HERE, "../rtl/pattern.v")],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call([os.path.join(mdir, "audio")], stdout=subprocess.DEVNULL)
    s = open(os.path.join(WORK, "audio_out.bin"), "rb").read()
    rec = [s[5 * k:5 * k + 5] for k in range(len(s) // 5)]
    flags = [(r[0] - 32) for r in rec]
    act = [f >> 7 & 1 for f in flags]
    pre = [f >> 6 & 1 for f in flags]
    de = [f >> 5 & 1 for f in flags]
    vs = [f >> 4 & 1 for f in flags]
    hs = [f >> 3 & 1 for f in flags]
    k0 = [((r[0] - 32) >> 1 & 3) << 8 | r[1] for r in rec]
    k1 = [(r[2] >> 6 & 3) << 8 | r[3] for r in rec]
    k2 = [(r[2] >> 4 & 3) << 8 | r[4] for r in rec]
    ok = True

    def bad(msg):
        nonlocal ok
        ok = False
        print("  WRONG:", msg)

    kinds = {}
    samples = []
    k = 1
    while k < len(act) - 40:
        if not (act[k] and not act[k - 1]):
            k += 1
            continue
        if pre[k - 8:k] != [1] * 8 or pre[k - 9]:
            bad("island at %d: the preamble is not the eight characters before" % k)
        if any(de[k - 20:k + 60]):
            bad("island at %d: within 20 characters of the picture" % k)
        if act[k:k + 36] != [1] * 36 or act[k + 36]:
            bad("island at %d: not 36 characters" % k)
        for j in (0, 1, 34, 35):
            if k1[k + j] != GB or k2[k + j] != GB or k0[k + j] != TERC4[0xC | vs[k + j] << 1 | hs[k + j]]:
                bad("island at %d: guard band character %d" % (k, j))
        try:
            n0 = [TERC4.index(v) for v in k0[k + 2:k + 34]]
            n1 = [TERC4.index(v) for v in k1[k + 2:k + 34]]
            n2 = [TERC4.index(v) for v in k2[k + 2:k + 34]]
        except ValueError:
            bad("island at %d: a character that is not TERC4" % k)
            k += 36
            continue
        if [v >> 3 for v in n0] != [0] + [1] * 31:
            bad("island at %d: channel 0's bit 3" % k)
        if any((v & 3) != (vs[k + 2 + j] << 1 | hs[k + 2 + j]) for j, v in enumerate(n0)):
            bad("island at %d: the syncs in channel 0" % k)
        hbits = [v >> 2 & 1 for v in n0]
        if bch(hbits[:24]) != sum(b << j for j, b in enumerate(hbits[24:])):
            bad("island at %d: the header's error correction" % k)
        hb = [sum(hbits[8 * j + i] << i for i in range(8)) for j in range(3)]
        subs = []
        for q in range(4):
            bits = []
            for j in range(32):
                bits += [n1[j] >> q & 1, n2[j] >> q & 1]
            if bch(bits[:56]) != sum(b << j for j, b in enumerate(bits[56:])):
                bad("island at %d: subpacket %d's error correction" % (k, q))
            subs.append([sum(bits[8 * j + i] << i for i in range(8)) for j in range(7)])
        kinds[hb[0]] = kinds.get(hb[0], 0) + 1
        if hb[0] in (0x82, 0x84):
            body = sum(subs, [])[:hb[2] + 1]
            if (sum(hb) + sum(body)) & 0xFF:
                bad("InfoFrame %02x: checksum" % hb[0])
        elif hb[0] == 0x01:
            for sb in subs:
                cts, nn = sb[1] << 16 | sb[2] << 8 | sb[3], sb[4] << 16 | sb[5] << 8 | sb[6]
                if (nn, cts) != (6144, 148352):
                    bad("N %d CTS %d" % (nn, cts))
        elif hb[0] == 0x02:
            for q in range(4):
                if hb[1] >> q & 1:
                    sb = subs[q]
                    l, r = sb[0] | sb[1] << 8 | sb[2] << 16, sb[3] | sb[4] << 8 | sb[5] << 16
                    samples.append((l, r, sb[6], hb[2] >> 4 + q & 1))
        else:
            bad("packet type %02x" % hb[0])
        k += 36
    # the samples: consecutive counts; the status bit and parity by their place in the block
    for j in range(1, len(samples)):
        if samples[j][0] != (samples[j - 1][0] + 1) & 0xFFFFFF or samples[j][1] != (samples[j - 1][1] - 3) & 0xFFFFFF:
            bad("sample %d does not follow the one before" % j)
            break
    starts = [j for j, sm in enumerate(samples) if sm[3]]
    if not starts or any(b - a != 192 for a, b in zip(starts, starts[1:])):
        bad("block starts at samples %s" % starts[:6])
    for j, (l, r, st, _) in enumerate(samples):
        if not starts:
            break
        n_ = (j - starts[0]) % 192
        c = CS[n_ // 8] >> n_ % 8 & 1 if n_ < 40 else 0
        want = (bin(r).count("1") + c) % 2 << 7 | c << 6 | (bin(l).count("1") + c) % 2 << 3 | c << 2
        if st != want and j >= starts[0]:
            bad("sample %d (place %d in its block): status %02x, want %02x" % (j, n_, st, want))
            break
    secs = len(rec) * 6.74e-9
    print("packets: %s; %d samples in %.1f ms (%.0f a second)" % (
        {"%02x" % t: c for t, c in sorted(kinds.items())}, len(samples), secs * 1e3, len(samples) / secs))
    print("audio islands: %s" % ("all as they should be" if ok else "WRONG"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
