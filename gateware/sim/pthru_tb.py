#!/usr/bin/env python3
"""pthru_tb.py [ll=N] [switch]: a 1280 x 720 progressive picture through the DDR3 and out as it came (Verilator): a
frame into rtl/vcap.v, cap_ddr.v and a model of the DDR3 (ddr_model.v), then a frame out of deint.v
(pg) and pthru.v beside pattern.v's 1280 x 720 timing (a pixel every other clock); every pixel
against the frame put in (4:4:4 and R'G'B' as pthru.v makes them).

ll=N: the frame shown is made from the one coming in, begun when N of its lines are in.
switch: pg is taken from deint.v in the middle of a step and given back: frames go on being made."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
W, H, LAT = 1280, 720, 10


def word(t, n, q):
    """frame t's word q of line n: {Cb, Y0, Cr, Y1}: steps and slopes, nothing a neighbour repeats"""
    v = (n * 37 + q * 11 + t * 101) & 0xFFFF
    y0 = 16 + (q * 3 + n) % 220
    y1 = 16 + (q * 3 + n * 5 + 1 + (v >> 3)) % 220
    cb = 16 + (v * 7 + n) % 225
    cr = 16 + ((v >> 2) * 13 + q) % 225
    return cb, y0, cr, y1


def stream(frames):
    """the pixel port's samples (C pins << 8 | Y pins): each frame after 3 lines of blanking, F 0"""
    out = []
    code = lambda xy: [b * 0x101 for b in (0xFF, 0, 0, xy)]
    for t in frames:
        for n in range(-3, H):
            v = 1 if n < 0 else 0
            nxt = 1 if n + 1 < 0 or n + 1 >= H else 0
            out += code(0x80 | v << 5)
            for q in range(W // 2):
                cb, y0, cr, y1 = word(t, n, q) if not v else (0x80, 0x10, 0x80, 0x10)
                out += [cb << 8 | y0, cr << 8 | y1]
            out += code(0x90 | nxt << 5)
            out += [0x8010] * 12
        out += code(0xA0) + [0x8010] * 16 + code(0xB0) + [0x8010] * 12
    return out


def rgb(y, cb, cr):
    clamp = lambda v: 0 if v < 0 else 255 if v > 0xFFFF else v >> 8
    yy = 298 * max(y - 16, 0) + 128
    return clamp(yy + 409 * (cr - 128)), clamp(yy - 100 * (cb - 128) - 208 * (cr - 128)), clamp(yy + 516 * (cb - 128))


def expect(t):
    mean = lambda a, b: (a + b + 1) >> 1
    out = []
    for n in range(H):
        ws = [word(t, n, q) for q in range(W // 2)]
        row = []
        for q, (cb, y0, cr, y1) in enumerate(ws):
            row.append(rgb(y0, cb, cr))
            if q + 1 < W // 2:
                row.append(rgb(y1, mean(cb, ws[q + 1][0]), mean(cr, ws[q + 1][2])))
            else:
                row.append(rgb(y1, cb, cr))
        out.append(row)
    return out


def main():
    os.makedirs(WORK, exist_ok=True)
    ll = int(next((a[3:] for a in sys.argv[1:] if a.startswith("ll=")), 0))
    sw = "switch" in sys.argv[1:]
    tag = "pt%s%s" % ("_ll%d" % ll if ll else "", "_sw" if sw else "")
    # (the first frame in is not counted: cap_ddr.v takes none it has not seen begin)
    frames = [0, 1, 2] if ll else [0, 1]
    data = stream(frames)
    open(os.path.join(WORK, tag + "_in.hex"), "w").write("\n".join("%04x" % b for b in data) + "\n")
    per = len(data) // len(frames)
    first_n = len(data) - per - 1 if ll else len(data) - 1
    # (ll: the second frame begun so that ll lines of it are in when the output's frame begins: FIRST
    # rows of 1650 pixels of 13.48 ns before row 0, less the three lines before the picture and ll lines:
    # a line here is 1300 samples of 13.468 ns)
    ll_wait = int(2 * 6.74 * 1650 * 750 - (3 + ll) * 1300 * 13.468)
    tb = '''`timescale 1ns/1ps
module tb;
    reg llc = 0; always #6.734 llc = ~llc;
    reg pclk = 0; always #5 pclk = ~pclk;
    reg clk = 0; always #3.37 clk = ~clk;
    reg pce = 1; always @(posedge clk) pce <= !pce;
    reg [15:0] mem [0:%(last)d];
    reg [15:0] y = 16'h8010;
    wire fb_we, eof, field; wire [16:0] fb_wa; wire [31:0] fb_wd; wire [9:0] w_ln, lines; wire [9:0] w_col;
    wire [10:0] pix; wire [15:0] nfields16; wire done; wire [18:0] raw_rd; wire f_we, f_wd; wire [7:0] f_wa;
    vcap u_cap (.llc(llc), .ncol(10'd640), .nlin(10'd720), .y(y[7:0]), .c(y[15:8]), .hs(1'b0), .vs(1'b0), .de(1'b0),
                .freeze(1'b0), .wide(1'b1), .we(fb_we), .wa(fb_wa), .wd(fb_wd), .w_ln(w_ln), .w_col(w_col), .eof(eof),
                .f_we(f_we), .f_wa(f_wa), .f_wd(f_wd), .pix(pix), .lines(lines), .field(field), .fields(nfields16),
                .arm(1'b0), .mode(2'd0), .done(done), .rclk(clk), .ra(10'd0), .rd(raw_rd));
    wire [9:0] f_prog; wire [2:0] f_pslot;
    wire ca_valid, ca_ack, db_valid, db_ack, db_rvalid; wire [24:0] ca_line, db_line; wire [255:0] ca_data, rd_data;
    wire [2:0] latest, fn; wire [7:0] par; wire [9:0] flines;
    reg [255:0] rd_q; always @(posedge pclk) rd_q <= rd_data;
    cap_ddr u_capd (.llc(llc), .nch(7'd80), .we(fb_we), .w_ln(w_ln), .w_col(w_col), .wd(fb_wd), .eof(eof), .eof_f(field),
                    .eof_lines(lines), .freeze(1'b0), .pclk(pclk), .a_valid(ca_valid), .a_line(ca_line),
                    .a_data(ca_data), .a_ack(ca_ack), .latest(latest), .par(par), .nfields(fn), .flines(flines),
                    .prog(f_prog), .prog_slot(f_pslot));
    wire cmd_ready, cmd_en, wr_en, rd_valid; wire [2:0] cmd; wire [28:0] addr; wire [255:0] wr_data;
    ddr_arb u_arb (.clk(pclk), .cmd_ready(cmd_ready), .cmd(cmd), .cmd_en(cmd_en), .addr(addr), .wr_data(wr_data),
                   .wr_data_en(wr_en), .rd_data_valid(rd_valid),
                   .a_valid(ca_valid), .a_line(ca_line), .a_data(ca_data), .a_ack(ca_ack),
                   .b_valid(db_valid), .b_line(db_line), .b_ack(db_ack), .b_rvalid(db_rvalid),
                   .c_valid(1'b0), .c_wr(1'b0), .c_line(25'd0), .c_data(256'd0), .c_ack(), .c_rvalid());
    ddr_model u_ddr (.clk(pclk), .cmd_ready(cmd_ready), .cmd(cmd), .cmd_en(cmd_en), .addr(addr), .wr_data(wr_data),
                     .wr_data_en(wr_en), .rd_data(rd_data), .rd_data_valid(rd_valid));
    wire ev, ev_first, r_we, fstart, hold; wire [9:0] goal, emitted, r_wa;
    wire [2:0] sd, si; wire [31:0] wd_d, wd_i;
    wire [15:0] frames; wire [7:0] dstate;
    deint u_deint (.clk(pclk), .nch(7'd80), .pg(pg_r), .ev(ev), .ev_first(ev_first), .goal(goal), .hold(hold),
                   .latest(latest), .par(par), .nfields(fn), .flines(flines), .mode(2'd0), .thr(8'd6), .nr(2'd2),
                   .ll(1'b%(ll_on)d), .ll_min(8'd%(ll)d), .prog(f_prog), .prog_slot(f_pslot), .top_f(1'b0),
                   .b_valid(db_valid), .b_line(db_line), .b_ack(db_ack), .b_rvalid(db_rvalid), .rd_data(rd_q),
                   .r_we(r_we), .r_slot_d(sd), .r_slot_i(si), .r_wa(r_wa), .r_wd_d(wd_d), .r_wd_i(wd_i),
                   .emitted(emitted), .fstart(fstart), .frames(frames), .state_o(dstate));
    wire de, hs, vs, pre, gb, ucc; wire [7:0] pr, pg, pb; wire [12:0] ox; wire [11:0] oy; wire [23:0] rgb;
    pattern u_pat (.clk(clk), .ce(pce), .hd(1'b1), .de(de), .hs(hs), .vs(vs), .pre(pre), .gb(gb), .ucc(ucc), .r(pr),
                   .g(pg), .b(pb), .ox(ox), .oy(oy));
    pthru u_pt (.w_clk(pclk), .r_we(r_we), .r_slot_d(sd[1:0]), .r_slot_i(si[1:0]), .r_wa(r_wa), .r_wd_d(wd_d),
                .r_wd_i(wd_i), .emitted(emitted), .hold(hold), .goal(goal), .clk(clk), .ce(pce), .swap(1'b0), .x(ox),
                .y(oy), .ev(ev), .ev_first(ev_first), .rgb(rgb));
    // the picture's timing beside pthru.v's pixel
    reg [%(lat)d:0] de_s = 0;
    always @(posedge clk) if (pce) de_s <= {de_s[%(lat)d - 1:0], de};
    wire de_d = de_s[%(lat)d - 1];
    integer f, i, j;
    reg llbit = 0;
    reg pg_r = 1;
    integer fr0;
    initial begin
        $readmemh("%(work)s/%(tag)s_in.hex", mem);
        for (i = 0; i <= %(first_n)d; i = i + 1) begin
            @(negedge llc); y = mem[i];
        end
        if (%(ll_on)d) begin
            @(posedge ev_first);
            #(%(ll_wait)d);
            fork
                for (j = %(first_n)d + 1; j <= %(last)d; j = j + 1) begin
                    @(negedge llc); y = mem[j];
                end
            join_none
        end else begin
            repeat (40) @(negedge llc);
            $display("frames in %%0d latest %%0d lines %%0d pix %%0d", fn, latest, flines, pix);
        end
        @(posedge ev_first);
        if (%(ll_on)d) $display("as the frame begins: %%0d lines of the frame in slot %%0d are in (latest %%0d)", f_prog, f_pslot, latest);
        if (%(sw)d) begin
            // pg taken away in the middle of a step, and given back: frames must go on being made
            #(3000000); @(posedge pclk); while (dstate[3:0] != 4'd2) @(posedge pclk);
            pg_r = 0; fr0 = frames;
            #(40000000); $display("switch: without pg %%0d frames more, state %%h", frames - fr0, dstate);
            @(posedge pclk); while (dstate[3:0] != 4'd2) @(posedge pclk);
            pg_r = 1; fr0 = frames;
            #(40000000); $display("switch: with pg again %%0d frames more, state %%h", frames - fr0, dstate);
            $finish;
        end
        f = $fopen("%(work)s/%(tag)s_out.bin", "wb");
        for (i = 0; i < %(n_out)d; i = i + 1) begin
            @(posedge clk); #0.1;
            if (i == 60000) llbit = dstate[4];
            if (!pce) $fwrite(f, "%%c%%c%%c%%c", 8'd65 + {7'd0, de_d}, rgb[23:16], rgb[15:8], rgb[7:0]);
        end
        $fclose(f);
        $display("deint: frames %%0d state %%h", frames, dstate);
        $display("ll %%0d", llbit);
        $finish;
    end
endmodule
''' % dict(last=len(data) - 1, first_n=first_n, ll_on=1 if ll else 0, ll=ll, ll_wait=ll_wait, lat=LAT,
           sw=1 if sw else 0, work=WORK, tag=tag, n_out=2 * (1650 * 750 + 1650 * 10))
    open(os.path.join(WORK, tag + "_tb.v"), "w").write(tb)
    rtl = [os.path.join(HERE, "../rtl", f) for f in ("vcap.v", "cap_ddr.v", "ddr_arb.v", "deint.v", "pthru.v", "pattern.v")]
    if os.environ.get("PT_DEINT"):      # (another deint.v: does the test catch what it is for)
        rtl[3] = os.environ["PT_DEINT"]
    mdir = os.path.join(WORK, "vl_" + tag)
    subprocess.check_call(["verilator", "--binary", "--timing", "-j", "16", "-Wno-fatal", "-Wno-WIDTH", "-Wno-UNUSED",
                           "-Wno-DECLFILENAME", "-Wno-STMTDLY", "-Wno-INITIALDLY", "-Wno-MULTIDRIVEN", "-Wno-TIMESCALEMOD",
                           "--top-module", "tb", "--Mdir", mdir, "-o", tag,
                           os.path.join(WORK, tag + "_tb.v"), os.path.join(HERE, "ddr_model.v")] + rtl,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = subprocess.check_output([os.path.join(mdir, tag)]).decode().strip()
    print(log)
    if sw:
        n = [int(l.split()[l.split().index("frames") - 1]) for l in log.splitlines() if l.startswith("switch:")]
        print("switch: %s" % ("frames go on" if len(n) == 2 and min(n) >= 2 else "STUCK"))
        return 0 if len(n) == 2 and min(n) >= 2 else 1
    s = open(os.path.join(WORK, tag + "_out.bin"), "rb").read()
    px = [s[4 * k + 1:4 * k + 4] for k in range(len(s) // 4) if s[4 * k] == 66]
    want = expect(frames[-1])
    print("%d pixels of picture out (a frame is %d)" % (len(px), W * H))
    bad, shown = 0, 0
    for n in range(H):
        for x in range(W):
            k = n * W + x
            if k >= len(px):
                bad += 1
                continue
            if tuple(px[k]) != want[n][x]:
                bad += 1
                if shown < 8:
                    print("  row %d column %d: got %s want %s" % (n, x, tuple(px[k]), want[n][x]))
                    shown += 1
    if ll:
        print("the frame was%s made from the one coming in" % ("" if "ll 1" in log.splitlines() else " NOT"))
    print("%s: %d wrong pixels of %d" % (tag, bad, W * H))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
