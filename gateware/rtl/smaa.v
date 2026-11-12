// smaa.v: the anti-aliasing: SMAA 1x's orthogonal patterns as sim/smaa.py has them (smaa_words()), on
// the stream of 4:2:2 lines (a pixel: luma and one chroma sample, Cb the even pixels, Cr the odd)
// before they are scaled.  On the DDR3's user clock.
//
// In: a line's pixels on successive clocks (i_v, i_x, i_j the line, i_last with the last), then
// 24 clocks or more of nothing; the lines in order from 0, and N + 4 more after the picture's last
// (H to H + N + 3: whatever).  Out: the same lines mixed, LAG = N + 3 lines later, and after the last
// one more (H: whatever is in it).
//
// A line is taken through as W + K columns, the K after the picture empty (K = N + 4): what looks N
// columns to each side then needs no thought for the picture's edge.  Three steps, each a column or
// two behind the one before:
//
//   edges    of the line before the one coming in (it wants the line below): for column x - 1 as
//            column x passes
//   weights  of the line N + 1 above the edges' (the edges of the 2N + 3 lines round it are kept for
//            each column): for the column N + 2 behind.  The four searches (left, right, up, down:
//            how far the edge runs, to N; which way it turns there), then the area table
//            ({the turns 4, the two lengths 4 each} -> {the part cut off above the edge, below})
//   mixing   of the line above the weights' (it wants the weights below): the pixel with the one of
//            its four neighbours whose weight is greatest; chroma with the one above or below only
//
// en 0: no edges, the picture through as it is (as late).  thr: the luma step that is an edge.
// dbg: what it finds, in the picture's place: the picture dimmed to a quarter and grey; a pixel
// with an edge and nothing mixed green; a pixel mixed with the one above or below blue, with the
// one beside it red, the brighter the more.

`ifndef SMAA_HEX
`define SMAA_HEX "smaa.hex"
`endif

module smaa_rom (
    input             clk,
    input      [11:0] a,
    output reg [15:0] q
);
    reg [15:0] mem [0:4095];
    initial $readmemh(`SMAA_HEX, mem);
    reg [15:0] q1;
    always @(posedge clk) begin
        q1 <= mem[a];
        q <= q1;
    end
endmodule

module smaa #(
    parameter W = 720,
    parameter H = 480,
    parameter N = 15
) (
    input             clk,
    input             en,
    input      [7:0]  thr,
    input             dbg,
    input             i_v,
    input      [9:0]  i_x,
    input      [9:0]  i_j,
    input             i_last,
    input      [7:0]  i_y,
    input      [7:0]  i_c,
    output reg        o_v = 1'b0,
    output reg [9:0]  o_x,
    output reg [9:0]  o_j,
    output reg        o_last,
    output reg [7:0]  o_y,
    output reg [7:0]  o_c
);
    localparam K = N + 4;
    integer i;
    function [7:0] absd(input [7:0] a, input [7:0] b);
        absd = a > b ? a - b : b - a;
    endfunction
    function [7:0] max2(input [7:0] a, input [7:0] b);
        max2 = a > b ? a : b;
    endfunction

    // ---- the columns: the line's, then K empty ones ----
    reg        t_v = 1'b0, t_b;
    reg [10:0] t_x;
    reg [9:0]  t_j;
    reg [7:0]  t_y, t_c;
    reg [5:0]  more = 6'd0;
    always @(posedge clk) begin
        t_v <= i_v || more != 6'd0;
        if (i_v) begin
            t_x <= {1'b0, i_x};
            t_j <= i_j;
            t_b <= 1'b0;
            t_y <= i_y;
            t_c <= i_c;
            more <= i_last ? K[5:0] : 6'd0;
        end else if (more != 6'd0) begin
            t_x <= t_x + 11'd1;
            t_b <= 1'b1;
            more <= more - 6'd1;
        end
    end

    // the pixels kept, 32 lines of them: for the mixing, N + 2 lines on
    reg [15:0] pm [0:32767];
    reg [14:0] p_ra;
    reg [15:0] p_q;
    always @(posedge clk) begin
        if (t_v && !t_b)
            pm[{t_j[4:0], t_x[9:0]}] <= {t_y, t_c};
        p_q <= pm[p_ra];
    end

    // ---- edges ----
    // each column's luma of the three lines before
    reg [23:0] am [0:1023];
    reg [23:0] a_r1;                    // (the RAM's register, then one beside the logic: as each RAM here)
    reg [23:0] a_q /* synthesis syn_preserve = 1 */;
    reg        e0_v = 1'b0, e0_b, e1_v = 1'b0, e1_b;
    reg [10:0] e0_x, e1_x;
    reg [9:0]  e0_j, e1_j;
    reg [7:0]  e0_y, e1_y;
    always @(posedge clk) begin
        a_r1 <= am[t_x[9:0]];
        a_q <= a_r1;
        {e1_v, e0_v} <= {e0_v, t_v};
        {e1_b, e0_b} <= {e0_b, t_b};
        {e1_x, e0_x} <= {e0_x, t_x};
        {e1_j, e0_j} <= {e0_j, t_j};
        {e1_y, e0_y} <= {e0_y, t_y};
        if (e1_v && !e1_b)
            am[e1_x[9:0]] <= {e1_y, a_q[23:8]};
    end
    // the line of the edges: e1_j - 1; this column's luma on it, above it, above that, below it
    wire [9:0] ee = e1_j - 10'd1;
    wire [7:0] cC = a_q[23:16];
    wire [7:0] cT = ee >= 10'd1 ? a_q[15:8] : cC;
    wire [7:0] cTT = ee >= 10'd2 ? a_q[7:0] : cT;
    wire [7:0] cB = ee <= H - 2 ? e1_y : cC;
    // the column before (the edges' own), and the two before it
    reg [7:0]  n1_c, n1_t, n1_tt, n1_b, n2_c, n3_c;
    reg        e2_v = 1'b0, e3_v = 1'b0;
    reg [10:0] e2_x, e3_x;
    reg [9:0]  e2_e, e3_e;
    reg [7:0]  dl, dt, dr, db, dll, dtt, mx3a, mx3b, mx3c, dl3, dt3;
    reg        g_v = 1'b0, g_el, g_et, e2_z, e3_z;
    reg [10:0] g_x;
    reg [9:0]  g_e;
    wire [10:0] xc = e1_x - 11'd1;
    wire [7:0]  mx = max2(max2(mx3a, mx3b), mx3c);
    always @(posedge clk) begin
        e2_v <= 1'b0;
        if (e1_v) begin
            n1_c <= cC;
            n1_t <= cT;
            n1_tt <= cTT;
            n1_b <= cB;
            n2_c <= n1_c;
            n3_c <= n2_c;
            // (2) the six steps round the column before
            e2_v <= e1_x != 11'd0 && e1_j != 10'd0;
            e2_x <= xc;
            e2_e <= ee;
            e2_z <= xc >= W || ee >= H || !en;
            dl <= xc == 11'd0 ? 8'd0 : absd(n1_c, n2_c);
            dt <= absd(n1_c, n1_t);
            dr <= xc >= W - 1 ? 8'd0 : absd(n1_c, cC);
            db <= absd(n1_c, n1_b);
            dll <= xc <= 11'd1 ? 8'd0 : absd(n2_c, n3_c);
            dtt <= absd(n1_t, n1_tt);
        end
        // (3) the greatest, two and two
        e3_v <= e2_v;
        e3_x <= e2_x;
        e3_e <= e2_e;
        e3_z <= e2_z;
        mx3a <= max2(dl, dt);
        mx3b <= max2(dr, db);
        mx3c <= max2(dll, dtt);
        dl3 <= dl;
        dt3 <= dt;
        // (4) the edges
        g_v <= e3_v;
        g_x <= e3_x;
        g_e <= e3_e;
        g_el <= !e3_z && dl3 >= thr && dl3 != 8'd0 && {1'b0, dl3, 1'b0} >= {2'b00, mx};
        g_et <= !e3_z && dt3 >= thr && dt3 != 8'd0 && {1'b0, dt3, 1'b0} >= {2'b00, mx};
    end

    // ---- weights ----
    // each column's edges of the 2N + 2 lines before (64 bits: line e - 1 lowest; a line {left, top})
    reg [63:0] bm [0:1023];
    reg [63:0] b_r1;
    reg [63:0] b_q /* synthesis syn_preserve = 1 */;
    reg        w0_v = 1'b0, w0_el, w0_et, w1_v = 1'b0, w1_el, w1_et;
    reg [10:0] w0_x, w1_x;
    reg [9:0]  w0_e, w1_e;
    always @(posedge clk) begin
        b_r1 <= bm[g_x[9:0]];
        b_q <= b_r1;
        {w1_v, w0_v} <= {w0_v, g_v};
        {w1_x, w0_x} <= {w0_x, g_x};
        {w1_e, w0_e} <= {w0_e, g_e};
        {w1_el, w0_el} <= {w0_el, g_el};
        {w1_et, w0_et} <= {w0_et, g_et};
        if (w1_v && w1_x < W)
            bm[w1_x[9:0]] <= {b_q[61:0], w1_el, w1_et};
    end
    // the column's 2N + 3 lines, e the lowest two bits; those above the picture's first empty
    reg [65:0] vm;
    always @* begin
        vm = w1_x < W ? {b_q, w1_el, w1_et} : 66'd0;
        for (i = 1; i <= 32; i = i + 1)
            if (i > w1_e) begin
                vm[2 * i] = 1'b0;
                vm[2 * i + 1] = 1'b0;
            end
    end
    // the columns before: all their lines for the last N + 3 (cv[k]: column w1_x - 1 - k); the
    // middle line's {top, left} and the line above's left for the last 2N + 3 (hk)
    reg [65:0] cv [0:17] /* synthesis syn_ramstyle = "registers" */;
    reg [2:0]  hk [0:32] /* synthesis syn_ramstyle = "registers" */;
    // the middle column: w1_x - 17, hk[16], cv[16]; the one before it cv[17]
    // hz(o): column middle + o, -16 <= o <= 16: {top, left, left of the line above}
    reg [15:0] ls, rs, us, ds;          // each search's stops
    reg [31:0] lc, rc, uc, dc;          // each's turns ({down or own, up or other}) at each step
    reg        s_v = 1'b0, s_et, s_el;
    reg [10:0] s_x;
    reg [9:0]  s_r;
    // (the lines of a column: line r + m is 16 - m lines back from e)
    `define ET(v, m) v[2 * (16 - (m))]
    `define EL(v, m) v[2 * (16 - (m)) + 1]
    always @(posedge clk) begin
        s_v <= 1'b0;
        if (w1_v) begin
            cv[0] <= vm;
            hk[0] <= {vm[32], vm[33], vm[35]};
            for (i = 1; i <= 17; i = i + 1)
                cv[i] <= cv[i - 1];
            for (i = 1; i <= 32; i = i + 1)
                hk[i] <= hk[i - 1];
            // the searches' steps, from the columns as they were (the middle one 17 behind this)
            s_v <= w1_x >= 11'd17 && w1_e >= 10'd16;
            s_x <= w1_x - 11'd17;
            s_r <= w1_e - 10'd16;
            s_et <= hk[16][2];
            s_el <= hk[16][1];
            for (i = 0; i < 16; i = i + 1) begin
                // left: the boundary on the left of column -i; right: on the right of column +i
                ls[i] <= hk[16 + i][1] | hk[16 + i][0] | !hk[16 + i + 1][2] | (i == 15);
                lc[2 * i +: 2] <= {hk[16 + i][1], hk[16 + i][0]};
                rs[i] <= hk[16 - i - 1][1] | hk[16 - i - 1][0] | !hk[16 - i - 1][2] | (i == 15);
                rc[2 * i +: 2] <= {hk[16 - i - 1][1], hk[16 - i - 1][0]};
                // up: the boundary above line -i; down: below line +i
                us[i] <= `ET(cv[16], -i) | `ET(cv[17], -i) | !`EL(cv[16], -i - 1) | (i == 15);
                uc[2 * i +: 2] <= {`ET(cv[16], -i), `ET(cv[17], -i)};
                ds[i] <= `ET(cv[16], i + 1) | `ET(cv[17], i + 1) | !`EL(cv[16], i + 1) | (i == 15);
                dc[2 * i +: 2] <= {`ET(cv[16], i + 1), `ET(cv[17], i + 1)};
            end
        end
    end
    // the first stop of each, and the turn there
    function [5:0] first(input [15:0] stop, input [31:0] turn);
        integer n;
        begin
            first = {turn[31:30], 4'd15};
            for (n = 14; n >= 0; n = n - 1)
                if (stop[n])
                    first = {turn[2 * n +: 2], n[3:0]};
        end
    endfunction
    reg        q_v = 1'b0, q_et, q_el, q2_v = 1'b0, q2_et, q2_el, q3_v = 1'b0, q3_et, q3_el;
    reg [10:0] q_x, q2_x, q3_x;
    reg [9:0]  q_r, q2_r, q3_r;
    reg [5:0]  fl, fr, fu, fd;
    wire [15:0] ah, av;                 // {above, below} of the top edge; {other side, own} of the left
    smaa_rom u_ah (.clk(clk), .a({fr[5:4], fl[5:4], fl[3:0], fr[3:0]}), .q(ah));
    smaa_rom u_av (.clk(clk), .a({fd[5:4], fu[5:4], fu[3:0], fd[3:0]}), .q(av));
    reg        k_v = 1'b0;
    reg [10:0] k_x;
    reg [9:0]  k_r;
    reg [7:0]  k_wt, k_wu, k_wl, k_wo;
    reg [1:0]  k_e;                     // the pixel's own edges {left, top}
    always @(posedge clk) begin
        q_v <= s_v;
        q_x <= s_x;
        q_r <= s_r;
        q_et <= s_et;
        q_el <= s_el;
        fl <= first(ls, lc);
        fr <= first(rs, rc);
        fu <= first(us, uc);
        fd <= first(ds, dc);
        {q3_v, q2_v} <= {q2_v, q_v};
        {q3_x, q2_x} <= {q2_x, q_x};
        {q3_r, q2_r} <= {q2_r, q_r};
        {q3_et, q2_et} <= {q2_et, q_et};
        {q3_el, q2_el} <= {q2_el, q_el};
        k_v <= q3_v;
        k_x <= q3_x;
        k_r <= q3_r;
        k_e <= {q3_el, q3_et};
        k_wt <= q3_et ? ah[7:0] : 8'd0;         // the pixel takes this much of the one above
        k_wu <= q3_et ? ah[15:8] : 8'd0;        // the one above this much of it
        k_wl <= q3_el ? av[7:0] : 8'd0;         // the pixel of the one to its left
        k_wo <= q3_el ? av[15:8] : 8'd0;        // the one to its left of it
    end

    // ---- mixing ----
    // each column's weights {top, left, of its left} of the line above; its pixels of the two lines
    // above the one the weights are of ({the nearer, the further})
    reg [25:0] cm [0:1023];
    reg [31:0] fm [0:1023];
    reg [25:0] c_r1;
    reg [31:0] f_r1;
    reg [25:0] c_q /* synthesis syn_preserve = 1 */;
    reg [31:0] f_q /* synthesis syn_preserve = 1 */;
    reg [15:0] p_d /* synthesis syn_preserve = 1 */;
    reg        b0_v = 1'b0, b1_v = 1'b0, b1_in;
    reg [10:0] b0_x, b1_x;
    reg [9:0]  b0_r, b1_r;
    reg [7:0]  b0_wt, b0_wu, b0_wl, b0_wo, b1_wt, b1_wu, b1_wl, b1_wo;
    reg [1:0]  b0_e, b1_e;
    always @* p_ra = {k_r[4:0], k_x[9:0]};
    always @(posedge clk) begin
        c_r1 <= cm[k_x[9:0]];
        f_r1 <= fm[k_x[9:0]];
        c_q <= c_r1;
        f_q <= f_r1;
        p_d <= p_q;
        {b1_v, b0_v} <= {b0_v, k_v};
        b1_in <= b0_x < W;
        {b1_x, b0_x} <= {b0_x, k_x};
        {b1_r, b0_r} <= {b0_r, k_r};
        {b1_wt, b0_wt} <= {b0_wt, k_wt};
        {b1_wu, b0_wu} <= {b0_wu, k_wu};
        {b1_wl, b0_wl} <= {b0_wl, k_wl};
        {b1_wo, b0_wo} <= {b0_wo, k_wo};
        {b1_e, b0_e} <= {b0_e, k_e};
        if (b1_v && b1_in) begin
            cm[b1_x[9:0]] <= {b1_e, b1_wt, b1_wl, b1_wo};
            fm[b1_x[9:0]] <= {p_d, f_q[31:16]};
        end
    end
    // the column before: its pixel (the line above the weights'), the ones above and below, its
    // weights; the luma to its left
    reg [15:0] v_ctr, v_top, v_bot;
    reg [7:0]  v_at, v_al, v_ab, v_ly;
    reg [1:0]  v_e, n_e, m_e, m2_e, m3_e;
    reg [7:0]  m2_w, m3_w;
    reg        m_vert, m2_vert, m3_vert;
    reg        m_v = 1'b0, n_v = 1'b0;
    reg [10:0] n_x;
    reg [9:0]  n_b;
    reg [7:0]  n_w, n_ly, n_ry;
    reg [1:0]  n_sel;
    reg [15:0] n_ctr, n_top, n_bot;
    reg [10:0] m_x;
    reg [9:0]  m_b;
    reg [7:0]  m_w, m_y, m_c, m_ny, m_nc;
    wire [7:0] a_r = b1_in ? c_q[7:0] : 8'd0;
    wire [7:0] best = max2(max2(v_at, v_ab), max2(v_al, a_r));
    wire signed [17:0] py, pc;
    easu_mul #(.AW(9), .BW(9)) u_my (.clk(clk), .a($signed({1'b0, m_ny}) - $signed({1'b0, m_y})), .b({1'b0, m_w}), .p(py));
    easu_mul #(.AW(9), .BW(9)) u_mc (.clk(clk), .a($signed({1'b0, m_nc}) - $signed({1'b0, m_c})), .b({1'b0, m_w}), .p(pc));
    reg        m2_v = 1'b0, m3_v = 1'b0;
    reg [10:0] m2_x, m3_x;
    reg [9:0]  m2_b, m3_b;
    reg [7:0]  m2_y, m2_c, m3_y, m3_c;
    wire signed [17:0] ry = py + 18'sd128, rc_ = pc + 18'sd128;
    always @(posedge clk) begin
        n_v <= 1'b0;
        if (b1_v) begin
            v_ctr <= f_q[31:16];
            v_top <= f_q[15:0];
            v_bot <= p_d;
            v_at <= c_q[23:16];
            v_al <= c_q[15:8];
            v_e <= c_q[25:24];
            v_ab <= b1_wu;
            v_ly <= v_ctr[15:8];
            // the pixel before this column's: which neighbour, how much
            n_v <= b1_x != 11'd0 && b1_x <= W && b1_r != 10'd0 && b1_r <= H + 1;
            n_x <= b1_x - 11'd1;
            n_b <= b1_r - 10'd1;
            n_w <= best;
            n_e <= v_e;
            n_sel <= best == v_at ? 2'd0 : best == v_ab ? 2'd1 : best == v_al ? 2'd2 : 2'd3;
            n_ctr <= v_ctr;
            n_top <= v_top;
            n_bot <= v_bot;
            n_ly <= v_ly;
            n_ry <= f_q[31:24];
        end
        // (a clock later) the neighbour itself
        m_v <= n_v;
        m_x <= n_x;
        m_b <= n_b;
        m_w <= n_w;
        m_e <= n_e;
        m_vert <= !n_sel[1];
        m_y <= n_ctr[15:8];
        m_c <= n_ctr[7:0];
        m_ny <= n_sel == 2'd0 ? n_top[15:8] : n_sel == 2'd1 ? n_bot[15:8] : n_sel == 2'd2 ? n_ly : n_ry;
        m_nc <= n_sel == 2'd0 ? n_top[7:0] : n_sel == 2'd1 ? n_bot[7:0] : n_ctr[7:0];
        m2_v <= m_v;
        m2_x <= m_x;
        m2_b <= m_b;
        m2_y <= m_y;
        {m3_e, m2_e} <= {m2_e, m_e};
        {m3_w, m2_w} <= {m2_w, m_w};
        {m3_vert, m2_vert} <= {m2_vert, m_vert};
        m2_c <= m_c;
        m3_v <= m2_v;
        m3_x <= m2_x;
        m3_b <= m2_b;
        m3_y <= m2_y;
        m3_c <= m2_c;
        o_v <= m3_v;
        o_x <= m3_x[9:0];
        o_j <= m3_b;
        o_last <= m3_x == W - 1;
        o_y <= m3_y + ry[15:8];
        o_c <= m3_c + rc_[15:8];
        if (dbg) begin
            if (m3_w != 8'd0) begin
                o_y <= 8'd128 + m3_w[7:1];
                o_c <= m3_vert == !m3_x[0] ? 8'd224 : 8'd96;        // (Cb the even pixels': blue up and down, red sideways)
            end else if (m3_e != 2'd0) begin
                o_y <= 8'd110;
                o_c <= 8'd64;
            end else begin
                o_y <= m3_y < 8'd16 ? 8'd16 : 8'd16 + {2'b00, m3_y[7:2]} - 8'd4;
                o_c <= 8'd128;
            end
        end
    end
endmodule
