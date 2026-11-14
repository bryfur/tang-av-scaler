// smaa_hist.v: the anti-aliasing's edges of the frame before, for smaa.v's edge step (keep: an edge
// that was there is kept more easily, one that was not needs more: sim/smaa.py edges(prev, keep)).
// A picture that stands still has noise; without this some of its edges come and go from frame to
// frame, and each takes the smoothing of a whole stretch of edge with it.
//
// Two bits a pixel ({top, left}), 1440 a line, a frame's 691 kbit: in the DDR3 (the arbiter's port
// e), a line six of the memory's 256-bit lines: in slot 0, each picture line's own 4096 bytes, from
// byte 3840 (no line's pixels reach it: 1920 of them end there: cap_ddr.v).  Here two small RAMs, a
// line and the next in each (by the line's low bit):
//   rm   the frame before's bits of the line smaa.v decides now, and of the next one (read ahead:
//        asked for when the line before it begins; a frame's first when the frame's lines begin)
//   wm   this frame's bits of the line decided now, and of the one before (written to the memory
//        when its line is over)
// smaa.v asks by the pixel's place three clocks before it wants the bits (r_x, r_l; p_e then), and
// says each pixel's edges as it decides them (g_*).  busy: a line is being read or written, or is
// to be: lstream.v begins no line then (so a line's bits are here before it is decided, and written
// before its place is another's; a line's two take some 350 clocks when the memory is free).

module smaa_hist #(
    parameter W = 720
) (
    input              clk,
    input      [2:0]   keep,            // 0: none of this (nothing asked of the memory)
    input              fstart,          // a frame's lines begin
    input      [9:0]   skip,            // ... at this line of the picture (the lines here count from it)
    input      [9:0]   h,               // the frame's lines
    input      [9:0]   r_x,
    input      [9:0]   r_l,
    output     [1:0]   p_e,             // {top, left}
    output             busy,
    input              g_v,
    input      [10:0]  g_x,
    input      [9:0]   g_e,
    input              g_el,
    input              g_et,
    // the memory (ddr_arb.v's port e; rd_data: the read's line with e_rvalid)
    output reg         e_valid = 1'b0,
    output reg         e_wr = 1'b0,
    output     [24:0]  e_line,
    output     [255:0] e_data,
    input              e_ack,
    input              e_rvalid,
    input      [255:0] rd_data
);
    wire       on = keep != 3'd0;

    // ---- the frame before's bits ----
    reg [15:0] rm [0:255];              // [{the line's low bit, the word (eight pixels) 0 to 95}]
    reg [7:0]  ra;
    reg [15:0] rq0, rq;
    reg [2:0]  rb0, rb1, rb2;
    reg        rm_we = 1'b0;
    reg [7:0]  rm_wa;
    reg [15:0] rm_wd;
    always @(posedge clk) begin
        ra <= {r_l[0], r_x[9:3]};
        rb0 <= r_x[2:0];
        rq0 <= rm[ra];
        rb1 <= rb0;
        rq <= rq0;
        rb2 <= rb1;
        if (rm_we)
            rm[rm_wa] <= rm_wd;
    end
    wire [15:0] rsh = rq >> {rb2, 1'b0};
    assign p_e = on ? rsh[1:0] : 2'b00;

    // ---- this frame's ----
    reg [15:0] wm [0:255];
    reg [13:0] pk;                      // (the word's pixels so far)
    reg [7:0]  wm_ra;
    reg [15:0] wq0, wq;
    wire       g_in = g_v && g_x < W && g_e < h;
    always @(posedge clk) begin
        if (g_in) begin
            pk <= {g_et, g_el, pk[13:2]};
            if (g_x[2:0] == 3'd7)
                wm[{g_e[0], g_x[9:3]}] <= {g_et, g_el, pk};
        end
        wq0 <= wm[wm_ra];
        wq <= wq0;
    end

    // ---- to and from the memory: a line's six words, read (ahead) or written (after) ----
    localparam S_IDLE = 3'd0, S_RREQ = 3'd1, S_RWAIT = 3'd2, S_RSTORE = 3'd3, S_WLOAD = 3'd4, S_WREQ = 3'd5;
    reg [2:0]  st = S_IDLE;
    reg        rd_pend = 1'b0, wr_pend = 1'b0;
    reg [9:0]  rd_l, wr_l, cur, skf = 10'd0;
    reg [2:0]  wn;                      // the word of the six
    reg [4:0]  cn;
    reg [255:0] dw;
    wire [9:0] abs_l = skf + cur;
    assign e_line = {8'd0, abs_l, 4'b1111, wn};
    assign busy = rd_pend || wr_pend || st != S_IDLE;
    assign e_data = dw;
    always @(posedge clk) begin
        rm_we <= 1'b0;
        // what is wanted: a line read ahead; a line written
        if (fstart) begin
            skf <= skip;
            rd_pend <= on;
            rd_l <= 10'd0;
            wr_pend <= 1'b0;
        end else if (on && g_v && g_x == 11'd0 && g_e + 10'd1 < h) begin
            rd_pend <= 1'b1;
            rd_l <= g_e + 10'd1;
        end
        if (on && g_v && g_x == W - 1 && g_e < h && !fstart) begin
            wr_pend <= 1'b1;
            wr_l <= g_e;
        end
        case (st)
            S_IDLE:
                if (rd_pend && !fstart) begin
                    rd_pend <= 1'b0;
                    cur <= rd_l;
                    wn <= 3'd0;
                    st <= S_RREQ;
                end else if (wr_pend && !fstart) begin
                    wr_pend <= 1'b0;
                    cur <= wr_l;
                    wn <= 3'd0;
                    cn <= 5'd0;
                    st <= S_WLOAD;
                end
            S_RREQ: begin
                e_valid <= 1'b1;
                e_wr <= 1'b0;
                if (e_valid && e_ack) begin
                    e_valid <= 1'b0;
                    st <= S_RWAIT;
                end
            end
            S_RWAIT:
                if (e_rvalid) begin
                    dw <= rd_data;
                    cn <= 5'd0;
                    st <= S_RSTORE;
                end
            S_RSTORE: begin             // the word's sixteen parts into rm, a clock each
                rm_we <= 1'b1;
                rm_wa <= {cur[0], wn, cn[3:0]};
                rm_wd <= dw[15:0];
                dw <= {16'd0, dw[255:16]};
                cn <= cn + 5'd1;
                if (cn == 5'd15) begin
                    wn <= wn + 3'd1;
                    st <= wn == 3'd5 ? S_IDLE : S_RREQ;
                end
            end
            S_WLOAD: begin              // sixteen parts out of wm (two clocks after their address) into the word
                wm_ra <= {cur[0], wn, cn[3:0]};
                if (cn >= 5'd3)
                    dw <= {wq, dw[255:16]};
                cn <= cn + 5'd1;
                if (cn == 5'd18)
                    st <= S_WREQ;
            end
            S_WREQ: begin
                e_valid <= 1'b1;
                e_wr <= 1'b1;
                if (e_valid && e_ack) begin
                    e_valid <= 1'b0;
                    e_wr <= 1'b0;
                    wn <= wn + 3'd1;
                    cn <= 5'd0;
                    st <= wn == 3'd5 ? S_IDLE : S_WLOAD;
                end
            end
            default: st <= S_IDLE;
        endcase
    end
endmodule
