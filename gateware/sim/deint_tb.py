#!/usr/bin/env python3
"""deint_tb.py [NFIELDS] [mode=M] [thr=T]: the picture's path through the DDR3 (iverilog): fields
with something moving in them into rtl/vcap.v, cap_ddr.v and a model of the DDR3 (ddr_model.v), then
a frame out of deint.v and lineview.v beside pattern.v's timing; every pixel of the frame against
model.py's deinterlacer and the scaling.  NFIELDS (default 5; 6: the newest field a bottom one)."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model

WORK = os.path.join(HERE, "build")
LAT, LINES = 10, 240


def stream(fields):
    """the pixel port's samples (C pins << 8 | Y pins) of the fields: model.field's words, each
    field after 3 lines of blanking"""
    out = []
    code = lambda xy: [b * 0x101 for b in (0xFF, 0, 0, xy)]
    for f, words in fields:
        for n in range(-3, LINES):
            v = 1 if n < 0 else 0
            nxt = 1 if n + 1 < 0 or n + 1 >= LINES else 0
            out += code(0x80 | f << 6 | v << 5)
            for q in range(360):
                cb, y0, cr, y1 = words[n][q] if not v else (0x80, 0x10, 0x80, 0x10)
                out += [cb << 8 | y0, cr << 8 | y1]
            out += code(0x90 | f << 6 | nxt << 5)
            out += [0x8010] * 12
        # (the blanking after the field: a line whose EAV says so)
        out += code(0xA0 | f << 6) + [0x8010] * 16 + code(0xB0 | f << 6) + [0x8010] * 12
    return out


def main():
    os.makedirs(WORK, exist_ok=True)
    args = sys.argv[1:]
    nf = int(next((a for a in args if a.isdigit()), 5))
    mode = int(next((a[5:] for a in args if a.startswith("mode=")), 0))
    thr = int(next((a[4:] for a in args if a.startswith("thr=")), 6))
    fields = [(t & 1, model.field(t)) for t in range(nf)]
    data = stream(fields)
    tag = "d%d_%d_%d" % (nf, mode, thr)
    open(os.path.join(WORK, tag + "_in.hex"), "w").write("\n".join("%04x" % b for b in data) + "\n")
    n_out = 2200 * 1125 + 2200 * 60
    tb = '''`timescale 1ns/1ps
module tb;
    reg llc = 0; always #8 llc = ~llc;
    reg pclk = 0; always #5 pclk = ~pclk;
    reg clk = 0; always #3.37 clk = ~clk;
    reg [15:0] mem [0:%(last)d];
    reg [15:0] y = 16'h8010;
    wire fb_we, eof, field; wire [16:0] fb_wa; wire [31:0] fb_wd; wire [9:0] w_ln, lines; wire [8:0] w_col;
    wire [10:0] pix; wire [15:0] nfields16; wire done; wire [18:0] raw_rd; wire f_we, f_wd; wire [7:0] f_wa;
    vcap u_cap (.llc(llc), .y(y[7:0]), .c(y[15:8]), .hs(1'b0), .vs(1'b0), .de(1'b0), .freeze(1'b0), .wide(1'b1),
                .we(fb_we), .wa(fb_wa), .wd(fb_wd), .w_ln(w_ln), .w_col(w_col), .eof(eof), .f_we(f_we), .f_wa(f_wa),
                .f_wd(f_wd), .pix(pix), .lines(lines), .field(field), .fields(nfields16), .arm(1'b0), .mode(2'd0),
                .done(done), .rclk(clk), .ra(10'd0), .rd(raw_rd));
    wire ca_valid, ca_ack, db_valid, db_ack, db_rvalid; wire [24:0] ca_line, db_line; wire [255:0] ca_data, rd_data;
    wire [2:0] latest, fn; wire [7:0] par; wire [9:0] flines;
    cap_ddr u_capd (.llc(llc), .we(fb_we), .w_ln(w_ln), .w_col(w_col), .wd(fb_wd), .eof(eof), .eof_f(field),
                    .eof_lines(lines), .freeze(1'b0), .pclk(pclk), .a_valid(ca_valid), .a_line(ca_line),
                    .a_data(ca_data), .a_ack(ca_ack), .latest(latest), .par(par), .nfields(fn), .flines(flines));
    wire cmd_ready, cmd_en, wr_en, rd_valid; wire [2:0] cmd; wire [28:0] addr; wire [255:0] wr_data;
    ddr_arb u_arb (.clk(pclk), .cmd_ready(cmd_ready), .cmd(cmd), .cmd_en(cmd_en), .addr(addr), .wr_data(wr_data),
                   .wr_data_en(wr_en), .rd_data_valid(rd_valid),
                   .a_valid(ca_valid), .a_line(ca_line), .a_data(ca_data), .a_ack(ca_ack),
                   .b_valid(db_valid), .b_line(db_line), .b_ack(db_ack), .b_rvalid(db_rvalid),
                   .c_valid(1'b0), .c_wr(1'b0), .c_line(25'd0), .c_data(256'd0), .c_ack(), .c_rvalid());
    ddr_model u_ddr (.clk(pclk), .cmd_ready(cmd_ready), .cmd(cmd), .cmd_en(cmd_en), .addr(addr), .wr_data(wr_data),
                     .wr_data_en(wr_en), .rd_data(rd_data), .rd_data_valid(rd_valid));
    reg [255:0] rd_q; always @(posedge pclk) rd_q <= rd_data;
    wire ev, ev_first, r_we; wire [8:0] ev_goal, r_wa; wire [2:0] sd, si; wire [31:0] wd_d, wd_i;
    wire [15:0] frames; wire [7:0] dstate;
    deint u_deint (.clk(pclk), .ev(ev), .ev_first(ev_first), .ev_goal(ev_goal), .latest(latest), .par(par),
                   .nfields(fn), .flines(flines), .mode(2'd%(mode)d), .thr(8'd%(thr)d), .top_f(1'b0),
                   .b_valid(db_valid), .b_line(db_line), .b_ack(db_ack), .b_rvalid(db_rvalid), .rd_data(rd_q),
                   .r_we(r_we), .r_slot_d(sd), .r_slot_i(si), .r_wa(r_wa), .r_wd_d(wd_d), .r_wd_i(wd_i),
                   .frames(frames), .state_o(dstate));
    wire de, hs, vs, pre, gb, ucc; wire [7:0] pr, pg, pb, r, g, b; wire [12:0] ox; wire [11:0] oy;
    pattern u_pat (.clk(clk), .de(de), .hs(hs), .vs(vs), .pre(pre), .gb(gb), .ucc(ucc), .r(pr), .g(pg), .b(pb),
                   .ox(ox), .oy(oy));
    lineview u_lv (.clk(clk), .de(de), .x(ox), .y(oy), .swap(1'b0), .ev(ev), .ev_first(ev_first), .ev_goal(ev_goal),
                   .w_clk(pclk), .w_we(r_we), .w_slot_d(sd), .w_slot_i(si), .w_wa(r_wa), .w_wd_d(wd_d),
                   .w_wd_i(wd_i), .r(r), .g(g), .b(b));
    reg [%(lat)d:0] dl = 0;
    always @(posedge clk) dl <= {dl, de};
    integer f, i;
    initial begin
        $readmemh("%(work)s/%(tag)s_in.hex", mem);
        for (i = 0; i <= %(last)d; i = i + 1) begin
            @(negedge llc); y = mem[i];
        end
        repeat (40) @(negedge llc);
        $display("fields %%0d latest %%0d par %%b lines %%0d pix %%0d", fn, latest, par, flines, pix);
        // the frame that begins after the fields are in: from the next end of row 1079
        @(posedge ev_first);
        f = $fopen("%(work)s/%(tag)s_out.bin", "wb");
        for (i = 0; i < %(n_out)d; i = i + 1) begin
            @(posedge clk); #0.1;
            $fwrite(f, "%%c%%c%%c%%c", 8'd65 + {7'd0, dl[%(lat)d]}, r, g, b);
        end
        $fclose(f);
        $display("deint: frames %%0d state %%h", frames, dstate);
        $finish;
    end
endmodule
''' % dict(last=len(data) - 1, mode=mode, thr=thr, lat=LAT - 1, work=WORK, tag=tag, n_out=n_out)
    open(os.path.join(WORK, tag + "_tb.v"), "w").write(tb)
    rtl = [os.path.join(HERE, "../rtl", f) for f in ("vcap.v", "cap_ddr.v", "ddr_arb.v", "deint.v", "lineview.v", "pattern.v")]
    subprocess.check_call(["iverilog", "-g2005", "-o", os.path.join(WORK, tag + ".vvp"), os.path.join(WORK, tag + "_tb.v"),
                           os.path.join(HERE, "ddr_model.v")] + rtl)
    print(subprocess.check_output(["vvp", "-n", os.path.join(WORK, tag + ".vvp")]).decode().strip())
    s = open(os.path.join(WORK, tag + "_out.bin"), "rb").read()
    de = [s[4 * k] - 65 for k in range(len(s) // 4)]
    start = next(k for k in range(1, len(de)) if de[k] and not de[k - 1])       # (the dump begins in blanking)
    want = model.frame_1080([w for _, w in fields], [f for f, _ in fields], mode, thr)
    bad = shown = 0
    for row in range(1080):
        base = 4 * (start + row * 2200)
        got = s[base:base + 4 * 1920]
        wrow = want[row]
        for col in range(1920):
            g3 = (got[4 * col + 1], got[4 * col + 2], got[4 * col + 3])
            if g3 != wrow[col]:
                bad += 1
                if shown < 10:
                    shown += 1
                    print("  row %d col %d: got %s want %s" % (row, col, g3, wrow[col]))
    print("%s: %d wrong pixels of %d" % (tag, bad, 1080 * 1920))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
