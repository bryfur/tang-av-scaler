// lstream.v: deint.v's lines, two at a time and sixteen pixels at a time, made a stream of whole
// lines in order, anti-aliased (smaa.v), 4:4:4, each pixel with its part of the scaler's edge
// analysis (sim/fsr.py analysis()), and written to easu.v's ring.  On the DDR3's user clock.
//
// - A store of four lines (words {Cb, Y0, Cr, Y1}; deint.v's r_*).  hold: deint.v waits (the two
//   lines before its last two are not read out yet).
// - Line j is read out when deint.v has made it and the output is near enough to wanting it
//   (j <= goal): a pixel a clock (its luma and one chroma sample), 48 clocks between lines.  After
//   the picture's last line FL more (whatever): smaa.v's lines come out LAG = FL - 1 lines late, and
//   the analysis wants a line after the last.
// - smaa.v; then 4:4:4: an even pixel has its word's chroma, an odd one the mean of its word's and
//   the next word's (the line's last its own).
// - As line j comes out of that, line j - 1 goes to the ring: each pixel with dx, dy (the luma to
//   its right less that to its left, below less above; at the picture's edge the pixel's own) and
//   ls = sx + sy, s = min(64, |d| RECIP[max(|far - mid|, |mid - near|)] / 64)^2 / 64.
//
// The ring's word (54 bits): {dx 9, dy 9, ls 8, 2'd0, y 8, cb 8, cr 8, 2'd0}.

module lstream #(
    parameter W = 720,
    parameter H = 480,
    parameter FL = 19                   // smaa.v's N + 4
) (
    input             clk,
    input             fstart,
    input      [9:0]  emitted,
    input      [10:0] goal,
    output reg        hold = 1'b0,      // (a clock after emitted)
    input             r_we,
    input      [1:0]  r_slot_d,
    input      [1:0]  r_slot_i,
    input      [8:0]  r_wa,
    input      [31:0] r_wd_d,
    input      [31:0] r_wd_i,
    input             aa_en,
    input             aa_dbg,
    input             aa_diag,
    input             aa_corner,
    input      [7:0]  aa_thr,

    output reg        w_we = 1'b0,
    output reg [2:0]  w_slot,
    output reg [9:0]  w_x,
    output reg [53:0] w_d
);
    // the store
    reg [8:0]  ra;
    reg [31:0] sq [0:3] /* synthesis syn_ramstyle = "registers" */;
    genvar k;
    generate
        for (k = 0; k < 4; k = k + 1) begin : g_st
            reg [31:0] mem [0:511];
            wire        wen = r_we && (r_slot_d == k || r_slot_i == k);
            wire [31:0] wd = r_slot_d == k ? r_wd_d : r_wd_i;
            always @(posedge clk) begin
                if (wen)
                    mem[r_wa] <= wd;
                sq[k] <= mem[ra];
            end
        end
    endgenerate

    // the read-out: line sj, word q: two clocks a word (ph 0 its first pixel, 1 its second); the
    // store's word at ra = q + 1 is there in the second
    reg [9:0]  sj = 10'd0;              // the line being or to be read out (from H: the last again)
    reg        run = 1'b0, ph = 1'b0, prime = 1'b0;
    reg [1:0]  pw;
    reg [5:0]  gap = 6'd0;
    reg [8:0]  q;
    reg [31:0] cur;
    wire [9:0] src = sj >= H ? H - 1 : sj;
    wire [31:0] nxt = sq[src[1:0]];
    wire       have = (sj < emitted || (sj >= H && emitted == H)) && sj < H + FL && {1'b0, sj} <= goal;
    always @(posedge clk)
        hold <= emitted - (sj > H ? H : sj) > 10'd2;
    reg        r_v = 1'b0, r_last = 1'b0;
    reg [9:0]  r_x, r_j;
    reg [7:0]  r_y, r_c;
    always @(posedge clk) begin
        r_v <= 1'b0;
        r_last <= 1'b0;
        if (gap != 6'd0)
            gap <= gap - 6'd1;
        if (fstart) begin
            sj <= 10'd0;
            run <= 1'b0;
            prime <= 1'b0;
        end else if (!run && !prime) begin
            if (have && gap == 6'd0) begin
                prime <= 1'b1;
                pw <= 2'd0;
                ra <= 9'd0;
            end
        end else if (prime) begin               // the first word, then the second's address
            pw <= pw + 2'd1;
            if (pw == 2'd1) begin
                cur <= nxt;
                ra <= 9'd1;
            end
            if (pw == 2'd2) begin
                prime <= 1'b0;
                run <= 1'b1;
                q <= 9'd0;
                ph <= 1'b0;
            end
        end else begin
            ph <= !ph;
            r_v <= 1'b1;
            r_j <= sj;
            r_x <= {q, ph};
            if (!ph) begin
                r_y <= cur[23:16];
                r_c <= cur[31:24];
            end else begin
                r_y <= cur[7:0];
                r_c <= cur[15:8];
                r_last <= q == W / 2 - 1;
                cur <= nxt;
                ra <= q + 9'd2;
                q <= q + 9'd1;
                if (q == W / 2 - 1) begin
                    run <= 1'b0;
                    sj <= sj + 10'd1;
                    gap <= 6'd47;         // (smaa.v takes a line through as W + NH + 4 columns)
                end
            end
        end
    end

    // the anti-aliasing
    wire       o_v, o_last;
    wire [9:0] o_x, o_j;
    wire [7:0] o_y, o_c;
    smaa #(.W(W), .H(H), .N(FL - 4)) u_aa (.clk(clk), .en(aa_en), .dbg(aa_dbg), .diag(aa_diag), .corner(aa_corner), .thr(aa_thr), .i_v(r_v), .i_x(r_x), .i_j(r_j),
                                         .i_last(r_last), .i_y(r_y), .i_c(r_c), .o_v(o_v), .o_x(o_x), .o_j(o_j),
                                         .o_last(o_last), .o_y(o_y), .o_c(o_c));

    // 4:4:4: the pixel two before the one coming in (and two clocks more at a line's end)
    reg [15:0] u0, u1, u2;
    reg [10:0] un;
    reg [9:0]  uj;
    reg [1:0]  umore = 2'd0;
    reg        s_v = 1'b0, s_last = 1'b0;
    reg [9:0]  s_x, s_j;
    reg [23:0] s_p;
    wire       u_t = o_v || umore != 2'd0;
    wire [10:0] n_in = o_v ? {1'b0, o_x} : un + 11'd1;
    wire [10:0] xo = n_in - 11'd2;
    function [7:0] mean(input [7:0] a, input [7:0] b);
        reg [8:0] t;
        begin
            t = {1'b0, a} + {1'b0, b} + 9'd1;
            mean = t[8:1];
        end
    endfunction
    always @(posedge clk) begin
        s_v <= 1'b0;
        s_last <= 1'b0;
        if (u_t) begin
            un <= n_in;
            if (o_v) begin
                uj <= o_j;
                umore <= o_last ? 2'd2 : 2'd0;
            end else
                umore <= umore - 2'd1;
            u0 <= {o_y, o_c};
            u1 <= u0;
            u2 <= u1;
            s_v <= n_in >= 11'd2;
            s_x <= xo[9:0];
            s_j <= o_v ? o_j : uj;
            s_last <= xo == W - 1;
            if (!xo[0])
                s_p <= {u1[15:8], u1[7:0], u0[7:0]};
            else if (xo == W - 1)
                s_p <= {u1[15:8], u2[7:0], u1[7:0]};
            else
                s_p <= {u1[15:8], mean(u2[7:0], u0[7:0]), mean(u1[7:0], o_c)};
        end
    end

    // the lines above: column x's pixel of the line before and luma of the line before that
    reg [31:0] lb [0:1023];
    reg [31:0] lbq;
    reg        a1_v = 1'b0, a1_last = 1'b0;
    reg [9:0]  a1_x, a1_j;
    reg [23:0] a1_p;
    always @(posedge clk) begin
        lbq <= lb[s_x];
        a1_v <= s_v;
        a1_last <= s_last;
        a1_x <= s_x;
        a1_j <= s_j;
        a1_p <= s_p;
        if (a1_v)
            lb[a1_x] <= {a1_p, lbq[31:24]};
    end

    // the line before, three pixels in a row: h1 the middle one, with the lumas above and below it;
    // a clock more at the line's end
    reg [23:0] h0_p, h1_p;
    reg [7:0]  h0_u, h0_d, h1_u, h1_d, h2_y;
    reg        h0_v = 1'b0, h1_v = 1'b0, fl = 1'b0, h1_first, h1_last;
    reg [9:0]  h0_x, h1_x, h_j;
    wire       c_v = a1_v && a1_j != 10'd0;
    always @(posedge clk) begin
        fl <= c_v && a1_last;
        h1_v <= 1'b0;
        if (c_v || fl) begin
            if (c_v) begin
                h0_p <= lbq[31:8];
                h0_u <= a1_j == 10'd1 ? lbq[31:24] : lbq[7:0];
                h0_d <= a1_j == H ? lbq[31:24] : a1_p[23:16];
                h0_x <= a1_x;
                h_j <= a1_j - 10'd1;
            end
            h0_v <= c_v;
            h1_v <= h0_v;
            h1_p <= h0_p;
            h1_u <= h0_u;
            h1_d <= h0_d;
            h1_x <= h0_x;
            h1_first <= h0_x == 10'd0;
            h1_last <= fl;
            h2_y <= h1_p[23:16];
        end
    end
    // the middle pixel's neighbours (its own at the edges); then the analysis in three steps
    wire [7:0] n_l = h1_first ? h1_p[23:16] : h2_y;
    wire [7:0] n_r = h1_last ? h1_p[23:16] : h0_p[23:16];
    function [7:0] absd(input [7:0] a, input [7:0] b);
        absd = a > b ? a - b : b - a;
    endfunction
    reg [12:0] recip [0:255];
    integer    n;
    initial begin
        recip[0] = 13'd0;
        for (n = 1; n < 256; n = n + 1)
            recip[n] = 4096 / n;
    end
    reg        p1_v = 1'b0, p2_v = 1'b0, p3_v = 1'b0;
    reg [9:0]  p1_x, p2_x, p3_x;
    reg [2:0]  p1_s, p2_s, p3_s;
    reg [23:0] p1_p, p2_p, p3_p;
    reg signed [8:0] p1_dx, p1_dy, p2_dx, p2_dy, p3_dx, p3_dy;
    reg [7:0]  p1_ax, p1_ay, p1_mx, p1_my;
    reg [12:0] p2_rx, p2_ry;
    reg [7:0]  p2_ax, p2_ay;
    wire [20:0] m_x = p2_ax * p2_rx, m_y = p2_ay * p2_ry;
    reg [6:0]  p3_tx, p3_ty;
    wire [13:0] sx2 = p3_tx * p3_tx, sy2 = p3_ty * p3_ty;
    always @(posedge clk) begin
        p1_v <= h1_v;
        p1_x <= h1_x;
        p1_s <= h_j[2:0];
        p1_p <= h1_p;
        p1_dx <= $signed({1'b0, n_r}) - $signed({1'b0, n_l});
        p1_dy <= $signed({1'b0, h1_d}) - $signed({1'b0, h1_u});
        p1_ax <= absd(n_r, n_l);
        p1_ay <= absd(h1_d, h1_u);
        p1_mx <= absd(n_r, h1_p[23:16]) > absd(h1_p[23:16], n_l) ? absd(n_r, h1_p[23:16]) : absd(h1_p[23:16], n_l);
        p1_my <= absd(h1_d, h1_p[23:16]) > absd(h1_p[23:16], h1_u) ? absd(h1_d, h1_p[23:16]) : absd(h1_p[23:16], h1_u);

        p2_v <= p1_v;
        p2_x <= p1_x;
        p2_s <= p1_s;
        p2_p <= p1_p;
        p2_dx <= p1_dx;
        p2_dy <= p1_dy;
        p2_ax <= p1_ax;
        p2_ay <= p1_ay;
        p2_rx <= recip[p1_mx];
        p2_ry <= recip[p1_my];

        p3_v <= p2_v;
        p3_x <= p2_x;
        p3_s <= p2_s;
        p3_p <= p2_p;
        p3_dx <= p2_dx;
        p3_dy <= p2_dy;
        p3_tx <= m_x[20:6] > 15'd64 ? 7'd64 : m_x[12:6];
        p3_ty <= m_y[20:6] > 15'd64 ? 7'd64 : m_y[12:6];

        w_we <= p3_v;
        w_slot <= p3_s;
        w_x <= p3_x;
        w_d <= {p3_dx, p3_dy, sx2[13:6] + sy2[13:6], 2'd0, p3_p, 2'd0};
    end
endmodule
