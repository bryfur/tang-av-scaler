// deint.v: the fields in the DDR3 (cap_ddr.v) made into a progressive picture, a line when the
// output wants it, motion adaptive: on the DDR3's user clock.
//
// At a frame's start the last four fields are taken: C the newest, then P1, P2, P3.  C's lines
// are the frame's lines of its parity as they are.  A line between two of them, `old` above and
// `new` below, is P1's line there (weave) where nothing moves and the mean of old and new (bob)
// where something does.  What moves: for each pixel
//
//   m = max(|C - P2| on old, on new, |P1 - P3| on the line itself)        (luma; two fields apart:
//                                                                           the same lines)
//   m' = max(m of the pixel before, m, m of the pixel after)              (within the 16 pixels of
//                                                                           a DDR3 line, and the
//                                                                           last of those before)
//   a = min(16, max(0, m' - thr))
//   out = (weave (16 - a) + bob a + 8) / 16                               (chroma: the pair's
//                                                                           greater a)
//
// At the picture's edge the missing one of old, new is the other.  mode 1: bob everywhere; 2: weave
// everywhere; bob too until four fields of alternating parity are there (hist).  top_f: the F of
// the top field.
//
// The lines go to lstream.v's store of four, 16 pixels at a time, two lines together (the one as it
// is, D, and the one made, I), eight words each (r_*: a line's place its number's low bits);
// emitted: the frame's lines all there; fstart: a clock at a frame's start.  hold: no new step (the
// store's lines are not read out yet).  The output asks by ev (a change: an event): ev_first with
// it: a new frame.  goal (this clock's): lines are made while emitted <= goal.
//
// A step k reads C's line k (new) into the place of line k - 1 (old, kept in cbuf with its |C - P2|
// in mbuf), and makes
//   C a top field     (k >= 1) D = line 2(k-1) = old, I = line 2(k-1)+1, P1's line k-1
//   C a bottom field  I = line 2k, P1's line k; D = line 2k+1 = new
// reading four lines of the DDR3 for each sixteen pixels (the fields' rows stay open: a slot is a
// bank).

module deint #(
    parameter NCH = 45                  // DDR3 lines (16 pixels) a line of picture
) (
    input              clk,
    input              ev,
    input              ev_first,
    input      [9:0]   goal,
    input              hold,
    input      [2:0]   latest,
    input      [7:0]   par,
    input      [2:0]   nfields,
    input      [9:0]   flines,
    input      [1:0]   mode,
    input      [7:0]   thr,
    input              top_f,

    output reg         b_valid = 1'b0,
    output reg [24:0]  b_line,
    input              b_ack,
    input              b_rvalid,
    input      [255:0] rd_data,

    output reg         r_we = 1'b0,     // both lines' word
    output reg [2:0]   r_slot_d,
    output reg [2:0]   r_slot_i,
    output reg [8:0]   r_wa,
    output reg [31:0]  r_wd_d,
    output reg [31:0]  r_wd_i,
    output reg [9:0]   emitted = 10'd0,
    output reg         fstart = 1'b0,
    output reg [15:0]  frames = 16'd0,  // (for the host: frames begun, and the last one's state)
    output reg [7:0]   state_o
);
    // the output's events
    reg        e0, e1, e2, start = 1'b0;
    reg        start_clr;
    always @(posedge clk) begin
        e0 <= ev;
        e1 <= e0;
        e2 <= e1;
        if (e1 != e2) begin
            if (ev_first)
                start <= 1'b1;
        end
        if (start_clr)
            start <= 1'b0;
    end

    localparam S_IDLE = 0, S_RQ = 1, S_WAIT = 2, S_C1 = 3, S_C2 = 4, S_W = 5, S_NEXT = 6, S_C1B = 7, S_C2B = 8,
               S_GO = 9, S_C1C = 10, S_GAP = 11, S_GAP2 = 12;
    reg [3:0]  st = S_IDLE;
    reg        active = 1'b0, pc, hist;
    reg [2:0]  fc, f1, f2, f3;          // the fields' slots
    reg [9:0]  nl;                      // a field's lines
    reg [9:0]  k;                       // the step
    reg [6:0]  c;                       // the sixteen pixels
    reg [2:0]  i;
    reg [2:0]  rx;
    reg [3:0]  p;
    reg [255:0] d0, d1, d2, d3;

    // the step's lines (registered: k changes between steps only, a clock at least before they
    // are used)
    wire [9:0] kmax = pc ? nl - 10'd1 : nl;
    reg        new_ok, old_ok, emit;
    reg [9:0]  row_new, row_w, line_i, line_d;
    always @(posedge clk) begin
        new_ok <= k < nl;
        old_ok <= k != 10'd0;
        emit <= pc ? 1'b1 : k != 10'd0;
        row_new <= k < nl ? k : nl - 10'd1;
        row_w <= pc ? k : (k != 10'd0 ? k - 10'd1 : 10'd0);
        line_i <= pc ? {k[8:0], 1'b0} : {k[8:0] - 9'd1, 1'b1};
        line_d <= pc ? {k[8:0], 1'b1} : {k[8:0] - 9'd1, 1'b0};
    end

    // old's line and its |C - P2|, by the sixteen pixels
    reg [255:0] cbuf [0:127];
    reg [127:0] mbuf [0:127];
    reg [255:0] old_c, oc1;             // (two registers after the RAM: its own, and one beside the logic)
    reg [127:0] old_m, om1;
    reg         buf_we;
    reg [6:0]   buf_a;                  // (its own register: a RAM with two ports, not one)
    reg [255:0] buf_c;
    reg [127:0] buf_m;
    always @(posedge clk) begin
        oc1 <= cbuf[c];
        om1 <= mbuf[c];
        old_c <= oc1;
        old_m <= om1;
        if (buf_we) begin
            cbuf[buf_a] <= buf_c;
            mbuf[buf_a] <= buf_m;
        end
    end

    // a DDR3 line's pixel n: its luma; pair q's word
    function [7:0] luma(input [255:0] d, input integer n);
        luma = n % 2 ? d[32 * (n / 2) +: 8] : d[32 * (n / 2) + 16 +: 8];
    endfunction
    function [7:0] absd(input [7:0] a, input [7:0] b);
        absd = a > b ? a - b : b - a;
    endfunction
    function [7:0] max2(input [7:0] a, input [7:0] b);
        max2 = a > b ? a : b;
    endfunction

    // C1: new and old as used, the three differences' greatest
    reg [127:0] dn, m, dnr, dwr, md, dor;
    reg         rdv = 1'b0;
    reg [255:0] rdq;
    reg [7:0]   carry;                  // m of the pixel before these sixteen
    reg [79:0]  al;                     // a, 5 bits a pixel
    integer     n;
    reg [7:0]   t_dn, t_do, t_dw, t_m, t_l, t_r, t_d;
    reg [8:0]   t_a;

    // W: a pair a clock, three stages: the pair's words, their means, the blend
    reg         s0_v = 1'b0;
    reg [8:0]   s0_wa;
    reg [31:0]  wo, wn, ww;
    reg [4:0]   a_y0, a_y1;
    wire [4:0]  a_c = a_y0 > a_y1 ? a_y0 : a_y1;
    reg         s1_v = 1'b0;
    reg [8:0]   s1_wa;
    reg [31:0]  s1_bob, s1_w, s1_d;
    reg [4:0]   s1_ay0, s1_ay1, s1_ac;
    function [7:0] mean(input [7:0] a, input [7:0] b);
        reg [8:0] t;
        begin
            t = {1'b0, a} + {1'b0, b} + 9'd1;
            mean = t[8:1];
        end
    endfunction
    function [7:0] blend(input [7:0] w, input [7:0] bb, input [4:0] a);
        reg [12:0] t;
        begin
            t = w * (5'd16 - a) + bb * a + 13'd8;
            blend = t[11:4];
        end
    endfunction

    always @(posedge clk) begin
        start_clr <= 1'b0;
        fstart <= 1'b0;
        buf_we <= 1'b0;
        s0_v <= 1'b0;
        s1_v <= s0_v;
        r_we <= s1_v;
        s1_wa <= s0_wa;
        s1_bob <= {mean(wo[31:24], wn[31:24]), mean(wo[23:16], wn[23:16]),
                   mean(wo[15:8], wn[15:8]), mean(wo[7:0], wn[7:0])};
        s1_w <= ww;
        s1_d <= pc ? wn : wo;
        s1_ay0 <= a_y0;
        s1_ay1 <= a_y1;
        s1_ac <= a_c;
        rdv <= b_rvalid;
        rdq <= rd_data;
        if (rdv) begin
            rx <= rx + 3'd1;
            case (rx[1:0])
                2'd0: d0 <= rdq;
                2'd1: d1 <= rdq;
                2'd2: d2 <= rdq;
                default: d3 <= rdq;
            endcase
        end
        case (st)
            S_IDLE:
                if (start) begin
                    start_clr <= 1'b1;
                    fstart <= 1'b1;
                    frames <= frames + 16'd1;
                    fc <= latest;
                    f1 <= latest - 3'd1;
                    f2 <= latest - 3'd2;
                    f3 <= latest - 3'd3;
                    pc <= par[latest] != top_f;
                    hist <= nfields >= 3'd4 && par[latest - 3'd1] != par[latest] &&
                            par[latest - 3'd2] == par[latest] && par[latest - 3'd3] != par[latest];
                    nl <= flines;
                    k <= 10'd0;
                    emitted <= 10'd0;
                    active <= nfields != 3'd0;
                end else if (active && !start_clr && !fstart && !hold && k <= kmax && emitted <= goal) begin
                    c <= 7'd0;
                    i <= 3'd0;
                    rx <= 3'd0;
                    carry <= 8'd0;
                    st <= S_GO;
                end
            S_GO:
                st <= S_RQ;
            S_RQ: begin                             // the four reads: C new, P2 new, P1, P3
                if (i == 3'd4) begin
                    if (b_ack) begin
                        b_valid <= 1'b0;
                        st <= S_WAIT;
                    end
                end else if (!b_valid || b_ack) begin
                    b_valid <= 1'b1;
                    b_line <= {i == 3'd0 ? fc : i == 3'd1 ? f2 : i == 3'd2 ? f1 : f3, 5'd0,
                               i[1] ? row_w : row_new, c};
                    i <= i + 3'd1;
                end
            end
            S_WAIT:
                if (rx == 3'd4)
                    st <= S_C1;
            // (the differences, the greatest of them and those with the pixels beside are worked out
            // below, a clock each, from the lines read and the buffers: both stay as they are until
            // the step is over)
            S_C1:
                st <= S_C1B;
            S_C1B:
                st <= S_C1C;
            S_C1C:
                st <= S_C2;
            S_C2: begin
                carry <= m[8 * 15 +: 8];
                st <= S_C2B;
            end
            S_C2B: begin
                for (n = 0; n < 16; n = n + 1) begin
                    t_m = md[8 * n +: 8];
                    t_d = t_m > thr ? t_m - thr : 8'd0;
                    al[5 * n +: 5] <= mode == 2'd1 || (!hist && mode != 2'd2) ? 5'd16 : mode == 2'd2 ? 5'd0 :
                                      t_d > 8'd16 ? 5'd16 : t_d[4:0];
                end
                p <= 4'd0;
                st <= emit ? S_W : S_NEXT;
            end
            S_GAP:
                st <= S_GAP2;
            S_GAP2:
                st <= S_IDLE;
            S_W: begin
                s0_v <= 1'b1;
                s0_wa <= {c[5:0], p[2:0]};
                wo <= old_ok ? old_c[32 * p[2:0] +: 32] : d0[32 * p[2:0] +: 32];
                wn <= new_ok ? d0[32 * p[2:0] +: 32] : old_c[32 * p[2:0] +: 32];
                ww <= d2[32 * p[2:0] +: 32];
                a_y0 <= al[5 * {p[2:0], 1'b0} +: 5];
                a_y1 <= al[5 * {p[2:0], 1'b1} +: 5];
                p <= p + 4'd1;
                if (p == 4'd7)
                    st <= S_NEXT;
            end
            S_NEXT: begin
                buf_we <= new_ok;                   // new's line and differences kept for the next step
                buf_a <= c;
                buf_c <= d0;
                buf_m <= dn;
                if (c == NCH - 1) begin
                    k <= k + 10'd1;
                    if (emit)
                        emitted <= emitted + 10'd2;
                    st <= S_GAP;                    // (two clocks: lstream.v's hold follows emitted)
                end else begin
                    c <= c + 7'd1;
                    i <= 3'd0;
                    rx <= 3'd0;
                    st <= S_RQ;
                end
            end
            default:
                st <= S_IDLE;
        endcase
        // C1 to C2B's work, a clock each (not held by the state)
        for (n = 0; n < 16; n = n + 1) begin
            dnr[8 * n +: 8] <= absd(luma(d0, n), luma(d1, n));
            dwr[8 * n +: 8] <= absd(luma(d2, n), luma(d3, n));
            t_dn = new_ok ? dnr[8 * n +: 8] : old_m[8 * n +: 8];
            dn[8 * n +: 8] <= t_dn;
            dor[8 * n +: 8] <= old_ok ? old_m[8 * n +: 8] : t_dn;
            m[8 * n +: 8] <= max2(max2(dn[8 * n +: 8], dor[8 * n +: 8]), dwr[8 * n +: 8]);
            t_l = n == 0 ? carry : m[8 * (n - 1) +: 8];
            t_r = n == 15 ? m[8 * 15 +: 8] : m[8 * (n + 1) +: 8];
            md[8 * n +: 8] <= max2(max2(t_l, m[8 * n +: 8]), t_r);
        end
        // the second stage: the word made, and the word as it is
        r_wa <= s1_wa;
        r_slot_d <= line_d[2:0];
        r_slot_i <= line_i[2:0];
        r_wd_d <= s1_d;
        r_wd_i <= {blend(s1_w[31:24], s1_bob[31:24], s1_ac), blend(s1_w[23:16], s1_bob[23:16], s1_ay0),
                   blend(s1_w[15:8], s1_bob[15:8], s1_ac), blend(s1_w[7:0], s1_bob[7:0], s1_ay1)};
        state_o <= {active, hist, pc, 1'b0, st};
    end
endmodule
