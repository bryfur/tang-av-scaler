// bicu.v: the scaler's last stage when the network (cnn.v) is its first: the network's luma, the
// picture at twice the size, stretched to the output by a bicubic kernel (sim/model.py scale_net(),
// bicubic_taps(): what the networks were trained with), and the chroma straight from the source by
// its four nearest.  It takes easu.v's place (the same raster in, the same clocks to the pixel out,
// the same events to the lines' side), asks cnn.v for its passes, and holds the two rings they
// fill:
//   the luma at twice the size: eight lines of 2 W (a line's place its number's low three bits)
//   the chroma: eight source lines of W, {cb, cr}
//
// A row's place in the source is yp (as easu.v's); in the picture at twice the size k = 2 yp + 1/2
// (its pixel n lies at the source's n / 2 - 1/4), to the nearest 32nd: the four lines L - 1 to
// L + 2 by the kernel's weights for the place; across the same from xq (less the sixteenth
// fsr.geom() adds for easu.v).  Down first (a column of four is one value), then across (four of
// those, a new one whenever the place moves on a pixel: it never moves more).
//
// The network's passes: the row three on wants the picture's lines up to L3 + 2, the source's
// (L3 + 2) / 2 = n_req: the passes are run up to it (a pass is two rows' time; with three rows in
// hand the eight lines' ring holds what the row now needs and what is written).  A pass n reads the
// source's lines up to n + 3 from easu.v's ring, so the lines' side is asked for lines up to
// n_req + 6, and no further than the next pass's oldest line + 7 (the ring has eight).
//
// A frame: ev_first goes to the lines' side, at the last row's end, or before it once this frame's
// lines are all in the ring (the lines' side then reads ahead, and puts nothing in the ring until
// the last row is over: the frame's first rows need lines sooner than easu.v does).  Its first
// line's number comes back (f_t changes: f_skip, the picture's first line: first); after the last
// row the passes begin: at first - 1, or two lines above the first one the output wants (n0) if that
// is lower down; the passes before n0 write nothing (they make layer 2's lines for it).

module bicu #(
    parameter W = 720,
    parameter H = 480
) (
    input              clk,
    input              on,              // the network's picture is the one shown (else nothing is asked of it)
    input              de,
    input      [12:0]  x,
    input      [11:0]  y,
    input              g_wide,
    input signed [27:0] g_xr,
    input      [16:0]  g_dx,
    input signed [26:0] g_ys,
    input      [16:0]  g_dy,
    // the lines' side
    output reg         ev = 1'b0,
    output reg         ev_first = 1'b0,
    output reg [9:0]   ev_goal = 10'd0,
    input              f_t,             // (its clock's) changes when a frame's lines begin: f_skip its first line
    input      [9:0]   f_skip,
    input              m_t,             // changes with m_made: the lines of the frame that are in easu.v's ring (the next one's number)
    input      [9:0]   m_made,
    // the network
    output reg         go = 1'b0,
    output reg signed [10:0] n,
    output reg         quiet = 1'b0,
    output reg [9:0]   first = 10'd0,
    output     [9:0]   last,
    input              busy,
    input              rdy,             // (cnn.v: a pass may be asked)
    input              o_we,
    input      [10:0]  o_line,
    input      [10:0]  o_col,
    input      [7:0]   o_d,
    input              c_we,
    input      [9:0]   c_line,
    input      [9:0]   c_col,
    input      [15:0]  c_d,
    // the pixel, LAT clocks after x
    output     [7:0]   o_y,
    output     [7:0]   o_cb,
    output     [7:0]   o_cr,
    output reg [15:0]  under = 16'd0    // rows begun before their lines were made (counted: there should be none)
) /* synthesis syn_srlstyle = "registers" */;      // (the short delays here are registers, not block RAM)
    localparam LAT = 26;
    reg on_q = 1'b0, u_x0 = 1'b0, u_late = 1'b0;
    assign last = H - 1;

    // the kernel: 32 places, four weights (256ths, signed 10 bits; 9:0 the pixel before the place's,
    // then its own, the next, the one after): sim/model.py bicubic_taps()
    function [39:0] taps(input [4:0] p);
        case (p)
            5'd0: taps = {10'sd0, 10'sd0, 10'sd256, 10'sd0};
            5'd1: taps = {10'sd0, 10'sd6, 10'sd256, -10'sd6};
            5'd2: taps = {-10'sd1, 10'sd13, 10'sd255, -10'sd11};
            5'd3: taps = {-10'sd2, 10'sd21, 10'sd252, -10'sd15};
            5'd4: taps = {-10'sd3, 10'sd29, 10'sd248, -10'sd18};
            5'd5: taps = {-10'sd4, 10'sd38, 10'sd243, -10'sd21};
            5'd6: taps = {-10'sd5, 10'sd47, 10'sd238, -10'sd24};
            5'd7: taps = {-10'sd7, 10'sd57, 10'sd232, -10'sd26};
            5'd8: taps = {-10'sd9, 10'sd67, 10'sd225, -10'sd27};
            5'd9: taps = {-10'sd11, 10'sd77, 10'sd218, -10'sd28};
            5'd10: taps = {-10'sd13, 10'sd88, 10'sd209, -10'sd28};
            5'd11: taps = {-10'sd15, 10'sd98, 10'sd201, -10'sd28};
            5'd12: taps = {-10'sd17, 10'sd109, 10'sd192, -10'sd28};
            5'd13: taps = {-10'sd19, 10'sd120, 10'sd182, -10'sd27};
            5'd14: taps = {-10'sd21, 10'sd131, 10'sd173, -10'sd27};
            5'd15: taps = {-10'sd22, 10'sd141, 10'sd162, -10'sd25};
            5'd16: taps = {-10'sd24, 10'sd152, 10'sd152, -10'sd24};
            5'd17: taps = {-10'sd25, 10'sd162, 10'sd141, -10'sd22};
            5'd18: taps = {-10'sd27, 10'sd173, 10'sd131, -10'sd21};
            5'd19: taps = {-10'sd27, 10'sd182, 10'sd120, -10'sd19};
            5'd20: taps = {-10'sd28, 10'sd192, 10'sd109, -10'sd17};
            5'd21: taps = {-10'sd28, 10'sd201, 10'sd98, -10'sd15};
            5'd22: taps = {-10'sd28, 10'sd209, 10'sd88, -10'sd13};
            5'd23: taps = {-10'sd28, 10'sd218, 10'sd77, -10'sd11};
            5'd24: taps = {-10'sd27, 10'sd225, 10'sd67, -10'sd9};
            5'd25: taps = {-10'sd26, 10'sd232, 10'sd57, -10'sd7};
            5'd26: taps = {-10'sd24, 10'sd238, 10'sd47, -10'sd5};
            5'd27: taps = {-10'sd21, 10'sd243, 10'sd38, -10'sd4};
            5'd28: taps = {-10'sd18, 10'sd248, 10'sd29, -10'sd3};
            5'd29: taps = {-10'sd15, 10'sd252, 10'sd21, -10'sd2};
            5'd30: taps = {-10'sd11, 10'sd255, 10'sd13, -10'sd1};
            5'd31: taps = {-10'sd6, 10'sd256, 10'sd6, 10'sd0};
        endcase
    endfunction

    // ---- the row (as easu.v): yp its place; at its end the next row's ----
    reg signed [26:0] yp = 27'sd0;
    reg [16:0] ypl;
    reg signed [10:0] yph;
    reg signed [26:0] ypn;
    reg        eol = 1'b0, lastr = 1'b0, row = 1'b0;
    reg [5:0]  eq = 6'd0;               // (the clocks after a row's end)
    reg        eq_first = 1'b0;
    always @(posedge clk) begin
        if (x == 13'd1918)
            row <= de;
        eol <= row && x == 13'd1958;
        lastr <= y == 12'd1079;
        ypl <= {1'b0, yp[15:0]} + {1'b0, g_dy[15:0]};
        yph <= yp[26:16] + {10'd0, g_dy[16]};
        ypn <= {yph + {10'd0, ypl[16]}, ypl[15:0]};
        if (eol)
            yp <= lastr ? g_ys : ypn;
        eq <= {eq[4:0], eol};
        if (eol)
            eq_first <= lastr;
    end
    // the row's lines and weights, in the clocks after its end:
    //   ky = 2 yp + 1/2 + 1/64: the line L and the place's 32nd; the four lines' places in the ring
    //   the chroma's two lines and its sixteenth
    //   the row three on: the source's line its last line wants
    function [10:0] lim2(input signed [12:0] v);        // a line of the picture at twice the size
        lim2 = v < 0 ? 11'd0 : v > 2 * H - 1 ? 2 * H - 1 : v[10:0];
    endfunction
    function [9:0] lim1(input signed [11:0] v);         // a line of the source
        lim1 = v < 0 ? 10'd0 : v > H - 1 ? H - 1 : v[9:0];
    endfunction
    wire signed [28:0] ky_w = {yp[26], yp, 1'b0} + 29'sd33792;
    reg signed [28:0] ky;
    reg signed [28:0] y3a, y3;
    reg signed [28:0] k3;
    reg [2:0]  rs [0:3];                // the four lines' places
    reg [39:0] wy;
    reg [2:0]  cs0, cs1;                // the chroma's two
    reg [4:0]  qy;                      // its sixteenth below the upper (0 to 15)
    reg [9:0]  need = 10'd0;            // the source's line the row now wants made
    reg [9:0]  n_req = 10'd0;           // ... and the row three on
    reg [9:0]  n_req_w;
    reg [9:0]  need_w;
    integer    i;
    always @(posedge clk) begin
        ky <= ky_w;
        // (three rows on: yp + 3 g_dy, in two steps)
        y3a <= {{2{yp[26]}}, yp} + {11'd0, g_dy, 1'b0};
        y3 <= y3a + {12'd0, g_dy};
        k3 <= {y3[27:0], 1'b0} + 29'sd33792;
        n_req_w <= lim2($signed(k3[28:16]) + 13'sd2) >> 1;
        need_w <= lim2($signed(ky[28:16]) + 13'sd2) >> 1;
        if (eq[2]) begin
            for (i = 0; i < 4; i = i + 1)
                rs[i] <= lim2($signed(ky[28:16]) + i - 1);
            wy <= taps(ky[15:11]);
            cs0 <= lim1($signed(yp[26:16]));
            cs1 <= lim1($signed(yp[26:16]) + 12'sd1);
            qy <= {1'b0, yp[15:12]};
        end
        if (eq[5]) begin
            n_req <= n_req_w;
            need <= need_w;
        end
    end

    // ---- the frame and the passes ----
    // the first line the output wants: n0 = (L0 - 1) / 2, L0 the first row's line (k0's whole part);
    // and the last row's place (g_ys + 1079 g_dy: the geometry stays as it is, a sum in steps) and
    // the source's line that row wants: n_fin
    wire signed [28:0] k0 = {g_ys[26], g_ys, 1'b0} + 29'sd33792;
    wire signed [12:0] l0m = $signed(k0r[28:16]) - 13'sd1;
    reg [9:0]  n0 = 10'd0;
    reg signed [28:0] yl1, yl2, yl3, yl4, yl5, kl, k0r;
    reg signed [10:0] n0m = 11'sd0, skm = 11'sd0;
    reg [9:0]  n_fin = 10'd0;
    reg [2:0]  f_s = 3'd0, m_s = 3'd0;
    reg [9:0]  made = 10'd0;            // the frame's lines in easu.v's ring: the next one's number
    reg        f_ok = 1'b0;             // the frame's passes go on (its lines have begun)
    // the next frame begun early on the lines' side: when every line this frame's passes read is in
    // the ring, the lines' side is told to begin the next (ev_first), with a goal that lets it read
    // ahead but put nothing in the ring (pre: its first line's number is the goal: the frame before's
    // is taken); at the last row's end the passes change over (its lines' count has been coming in
    // meanwhile: made is the next frame's from f_new on)
    reg        pre = 1'b0, f_new = 1'b0, f_end = 1'b0, asked = 1'b0;
    reg [9:0]  sk_was = 10'd0, sk_new = 10'd0;
    reg signed [10:0] n_next = 11'sd0;  // the next pass
    reg signed [10:0] n_done = -11'sd2; // the last one finished
    reg        busy_q = 1'b0;
    reg        gq = 1'b0 /* synthesis syn_preserve = 1 */;       // (go, a copy for what is decided here)
    reg        rdy_q = 1'b0;            // (cnn.v's rdy, a clock late: by the third clock after a go it is off)
    reg signed [10:0] n_st_r = 11'sd0;
    reg [9:0]  n_out_w = 10'd0;
    reg [10:0] ga_r = 11'd0, gb_r = 11'd0;
    wire signed [11:0] top = n_next + 11'sd3 > $signed({2'b00, last}) ? $signed({2'b00, last}) : n_next + 11'sd3;
    wire [10:0] fin3 = {1'b0, n_fin} + 11'd3 > {1'b0, last} ? {1'b0, last} : {1'b0, n_fin} + 11'd3;
    wire       all_in = !f_new && {1'b0, made} > fin3;      // (this frame's lines are all in the ring)
    wire       can = on && f_ok && rdy_q && !gq && !busy_q && n_next <= $signed({1'b0, n_req}) &&
                     (f_new || $signed({2'b00, made}) > top);
    // (what follows is in no hurry: each step a register)
    reg        can_r = 1'b0, all_r = 1'b0;
    reg [9:0]  old_r = 10'd0;
    reg [10:0] gl_r = 11'd0;
    reg [9:0]  goal_x = 10'd0;
    // the goal: lines up to n_req + 6, no further than the next pass's oldest + 7 (the oldest line
    // the next pass reads: the last pass's own; before a frame's passes: three above n0)
    wire [9:0] old = f_ok && n_done > $signed({1'b0, first}) ? n_done[9:0] : f_ok ? first : n0 > 10'd3 ? n0 - 10'd3 : 10'd0;
    wire [10:0] g_a = {1'b0, n_req} + 11'd6, g_b = {1'b0, old_r} + 11'd7;
    wire [10:0] g_l = ga_r < gb_r ? ga_r : gb_r;
    // where a frame's passes begin, and the first that writes
    wire signed [10:0] n_st = n0m > skm ? n0m : skm;
    reg [9:0]  n_out = 10'd0;
    reg [9:0]  goal_w = 10'd0;
    reg        ev_want = 1'b0, ev_wf = 1'b0;
    reg [4:0]  ev_gap = 5'd0;
    reg [2:0]  ev_hold = 3'd0;
    always @(posedge clk) begin
        k0r <= k0;
        n0 <= lim1($signed(l0m[12:1]));
        // (1079 = 1024 + 32 + 16 + 4 + 2 + 1: a sum a clock; the geometry stays as it is)
        yl1 <= {{2{g_ys[26]}}, g_ys} + {2'd0, g_dy, 10'd0};
        yl2 <= {7'd0, g_dy, 5'd0} + {8'd0, g_dy, 4'd0};
        yl3 <= {10'd0, g_dy, 2'd0} + {11'd0, g_dy, 1'b0} + {12'd0, g_dy};
        yl4 <= yl1 + yl2;
        yl5 <= yl4 + yl3;
        kl <= {yl5[27:0], 1'b0} + 29'sd33792;
        n0m <= $signed({1'b0, n0}) - 11'sd2;
        skm <= $signed({1'b0, sk_new}) - 11'sd1;
        n_fin <= lim2($signed(kl[28:16]) + 13'sd2) >> 1;
        f_s <= {f_s[1:0], f_t};
        m_s <= {m_s[1:0], m_t};
        if (m_s[2] != m_s[1])
            made <= m_made;
        busy_q <= busy;
        go <= 1'b0;
        gq <= 1'b0;
        can_r <= can;
        all_r <= all_in;
        old_r <= old;
        ga_r <= g_a;
        gb_r <= g_b;
        gl_r <= g_l;
        rdy_q <= rdy;
        n_st_r <= n_st;
        n_out_w <= n0 > sk_new ? n0 : sk_new;
        if (eq[0] && eq_first) begin                    // the last row is over
            f_end <= 1'b1;
            if (f_end && asked && !f_new) begin         // (a frame ago the lines' side was told, and nothing came: again)
                asked <= 1'b0;
                pre <= 1'b0;
            end
        end
        if (f_s[2] != f_s[1]) begin                     // the next frame's lines begin (on the lines' side)
            f_new <= 1'b1;
            sk_new <= f_skip;
        end
        if (f_end && !asked) begin
            // the lines' side is told of the next frame now (no early start was made)
            asked <= 1'b1;
            f_ok <= 1'b0;
            ev_want <= 1'b1;
            ev_wf <= 1'b1;
            ev_hold <= 3'd6;
        end else if (f_end && asked && f_new && rdy_q && !busy_q && !gq) begin
            // the change-over: the next frame's passes
            f_end <= 1'b0;
            asked <= 1'b0;
            pre <= 1'b0;
            f_new <= 1'b0;
            f_ok <= 1'b1;
            first <= sk_new;
            sk_was <= sk_new;
            n_next <= n_st_r;
            n_done <= n_st_r - 11'sd1;
            n_out <= n_out_w;
        end else if (on && f_ok && !asked && !f_end && all_r) begin
            // this frame's lines are all in: the next begun early
            asked <= 1'b1;
            pre <= 1'b1;
            ev_want <= 1'b1;
            ev_wf <= 1'b1;
            ev_hold <= 3'd6;
        end else if (can_r && rdy_q && !gq) begin
            go <= 1'b1;
            gq <= 1'b1;
            n <= n_next;
            quiet <= n_next < $signed({1'b0, n_out});
            n_next <= n_next + 11'sd1;
        end
        if (busy_q && !busy)
            n_done <= n;
        // the goal, said again when it has changed (and at a frame's start, with ev_first: that one
        // after the goal has taken what the frame's start changes in it: ev_hold)
        goal_w <= pre ? sk_was : gl_r >= H - 1 ? H : gl_r[9:0] + 10'd1;
        goal_x <= goal_w;
        if (ev_hold != 3'd0)
            ev_hold <= ev_hold - 3'd1;
        if (goal_x != ev_goal && goal_x == goal_w && !ev_wf)
            ev_want <= 1'b1;
        if (ev_gap != 5'd0)
            ev_gap <= ev_gap - 5'd1;
        else if (ev_want && ev_hold == 3'd0 && goal_x == goal_w) begin
            ev <= !ev;
            ev_first <= ev_wf;
            ev_goal <= goal_x;
            ev_want <= 1'b0;
            ev_wf <= 1'b0;
            ev_gap <= 5'd31;
        end
        // (a row's first pixel: its lines must be there)
        // (counted while the network is the picture shown, from when it is made so)
        on_q <= on;
        if (on && !on_q)
            under <= 16'd0;
        else if (on && u_x0 && u_late && under != 16'hFFFF)
            under <= under + 16'd1;
        // (a row's first pixel, and its lines not there: a clock before they are counted: registers,
        // so the count is no part of the raster's own paths)
        u_x0 <= de && x == 13'd0;
        u_late <= !f_ok || n_done < $signed({1'b0, need});
    end

    // ---- the place across (as easu.v's xq: the pixel's now at x), kept as what is wanted of it: ----
    // the luma's kx = 2 (xq - 1/16) + 1/2 + 1/64; the chroma's xc = xq - 1/16
    reg        x_at = 1'b0;
    reg signed [29:0] kx = 30'sd0, k_0 = 30'sd0;
    reg signed [27:0] xc = 28'sd0, c_0 = 28'sd0;
    always @(posedge clk) begin
        x_at <= x == 13'd2079;
        k_0 <= {g_xr[27], g_xr, 1'b0} + 30'sd25600;             // (the line's first: the geometry stays as it is)
        c_0 <= g_xr - 28'sd4096;
        kx <= (x_at ? k_0 : kx) + $signed({12'd0, g_dx, 1'b0});
        xc <= (x_at ? c_0 : xc) + $signed({11'd0, g_dx});
    end
    wire signed [14:0] cn = $signed(kx[29:16]) + 15'sd2;       // the newest of the four columns
    wire signed [12:0] cc = $signed(xc[27:16]) + 13'sd1;       // the chroma's right one
    reg        kb = 1'b0, cb_ = 1'b0;
    reg [10:0] ra_n;
    reg [9:0]  rc_n;
    reg [11:0] adv = 12'd0, adc = 12'd0;        // ([k]: of the pixel k + 1 clocks on: its place has moved on a pixel)
    reg [4:0]  px [0:9];
    reg [3:0]  qx [0:9];
    always @(posedge clk) begin
        kb <= kx[16];
        cb_ <= xc[16];
        adv <= {adv[10:0], kx[16] != kb};
        adc <= {adc[10:0], xc[16] != cb_};
        ra_n <= cn < 0 ? 11'd0 : cn > 2 * W - 1 ? 2 * W - 1 : cn[10:0];
        rc_n <= cc < 0 ? 10'd0 : cc > W - 1 ? W - 1 : cc[9:0];
        px[0] <= kx[15:11];
        qx[0] <= xc[15:12];
        for (i = 1; i < 10; i = i + 1) begin
            px[i] <= px[i - 1];
            qx[i] <= qx[i - 1];
        end
    end

    // ---- the rings: a line a RAM, read all at once ----
    reg [7:0]  q [0:7];
    reg [15:0] qc [0:7];
    genvar g;
    generate
        for (g = 0; g < 8; g = g + 1) begin : g_ring
            reg [7:0]  m [0:2047];
            reg [10:0] ra /* synthesis syn_preserve = 1 */;
            reg [7:0]  q1;
            reg        wen;
            reg [10:0] wa;
            reg [7:0]  wd;
            always @(posedge clk) begin
                wen <= o_we && o_line[2:0] == g;
                wa <= o_col;
                wd <= o_d;
                if (wen)
                    m[wa] <= wd;
                ra <= ra_n;
                q1 <= m[ra];
                q[g] <= q1;
            end
            reg [15:0] mc [0:1023];
            reg [9:0]  rc /* synthesis syn_preserve = 1 */;
            reg [15:0] qc1;
            reg        cen;
            reg [9:0]  ca;
            reg [15:0] cd;
            always @(posedge clk) begin
                cen <= c_we && c_line[2:0] == g;
                ca <= c_col;
                cd <= c_d;
                if (cen)
                    mc[ca] <= cd;
                rc <= rc_n;
                qc1 <= mc[rc];
                qc[g] <= qc1;
            end
        end
    endgenerate

    // ---- the luma: the column's four lines by the row's weights; four columns by the place's ----
    // (clocks after the pixel's x: 1 the column asked, 2 the RAMs' address, 3, 4 their words, 5 the
    // four lines, 6, 7 the products, 8 the column's value, 9 the window, 10, 11 the products, 12 their
    // sum, 13 the pixel)
    reg [7:0]  l4 [0:3];
    wire signed [18:0] pv [0:3];
    reg signed [19:0] vcol;
    reg signed [19:0] vw [0:3];
    reg [39:0] wxr;
    wire signed [29:0] ph [0:3];
    reg signed [31:0] hsum;
    reg [7:0]  yo;
    generate
        for (g = 0; g < 4; g = g + 1) begin : g_v
            easu_mul #(.AW(9), .BW(10)) u (.clk(clk), .a({1'b0, l4[g]}), .b(wy[10 * g +: 10]), .p(pv[g]));
            easu_mul #(.AW(20), .BW(10)) uh (.clk(clk), .a(vw[g]), .b(wxr[10 * g +: 10]), .p(ph[g]));
        end
    endgenerate
    wire signed [31:0] hr = hsum + 32'sd32768;
    always @(posedge clk) begin
        for (i = 0; i < 4; i = i + 1)
            l4[i] <= q[rs[i]];
        vcol <= pv[0] + pv[1] + pv[2] + pv[3];
        if (adv[7]) begin
            vw[3] <= vcol;
            vw[2] <= vw[3];
            vw[1] <= vw[2];
            vw[0] <= vw[1];
        end
        wxr <= taps(px[7]);
        hsum <= ph[0] + ph[1] + ph[2] + ph[3];
        yo <= hr < 0 ? 8'd0 : hr[31:16] > 16'sd255 ? 8'd255 : hr[23:16];
    end

    // ---- the chroma: the two lines by the row's sixteenth, two columns by the place's ----
    // (1 the column asked, 2 the address, 3, 4 the words, 5 the two lines, 6 the products, 7 the
    // column's value, 8 the window, 9 the products, 10 the pixel)
    reg [15:0] c0, c1;
    reg [12:0] m0 [0:1], m1 [0:1];
    reg [12:0] cv [0:1], cw0 [0:1], cw1 [0:1];
    reg [17:0] h0 [0:1], h1 [0:1];
    reg [7:0]  co [0:1];
    wire [4:0] qxa = {1'b0, qx[7]};
    always @(posedge clk) begin
        c0 <= qc[cs0];
        c1 <= qc[cs1];
        for (i = 0; i < 2; i = i + 1) begin
            m0[i] <= (5'd16 - qy) * c0[8 * i +: 8];
            m1[i] <= qy * c1[8 * i +: 8];
            cv[i] <= m0[i] + m1[i];
            if (adc[6]) begin
                cw1[i] <= cv[i];
                cw0[i] <= cw1[i];
            end
            h0[i] <= (5'd16 - qxa) * cw0[i];
            h1[i] <= qxa * cw1[i];
            co[i] <= (h0[i] + h1[i] + 18'd128) >> 8;
        end
    end

    // ---- the pixel, LAT clocks after x ----
    reg [8 * (LAT - 13) - 1:0] dy;
    reg [16 * (LAT - 10) - 1:0] dc;
    always @(posedge clk) begin
        dy <= {dy[8 * (LAT - 14) - 1:0], yo};
        dc <= {dc[16 * (LAT - 11) - 1:0], co[1], co[0]};
    end
    assign o_y = dy[8 * (LAT - 13) - 1 -: 8];
    assign {o_cb, o_cr} = dc[16 * (LAT - 10) - 1 -: 16];
endmodule
