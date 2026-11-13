// pthru.v: a progressive picture sent as it came, pixel for pixel (1280 x 720 in, 1280 x 720 out):
// deint.v's lines (pg: the frame's own, two a step) through a store of four straight to the
// output; nothing anti-aliased, scaled or sharpened.
//
// - The store: four lines of 640 words {Cb, Y0, Cr, Y1}, written as lstream.v's is (deint.v's r_*,
//   on the DDR3's user clock), a line's place its number's low two bits.
// - The output reads it by its own place: x, y are pattern.v's (on the word clock, a pixel each
//   ce); the pixel is out LAT pixels later.  An even pixel has its word's chroma, an odd one the
//   mean of its word's and the next word's (the line's last its own), as lstream.v makes 4:4:4;
//   R'G'B' as rcas.v's (BT.601, 16 to 235).
// - What deint.v is asked for, as easu.v asks: an event (ev changes) FIRST rows before the
//   picture's first: a new frame; then one as each row begins.  On the DDR3's clock from those:
//   goal (lines are made while emitted <= goal) and hold (the store's lines of the two rows after
//   the one being read are there: no more yet).

module pthru #(
    parameter W = 1280,
    parameter H = 720,
    parameter VT = 750,
    parameter FIRST = 3
) (
    input             w_clk,
    input             r_we,
    input      [1:0]  r_slot_d,
    input      [1:0]  r_slot_i,
    input      [9:0]  r_wa,
    input      [31:0] r_wd_d,
    input      [31:0] r_wd_i,
    input      [9:0]  emitted,
    output reg        hold = 1'b0,
    output reg [9:0]  goal = 10'd0,

    input             clk,
    input             ce,
    input             swap,             // Cb and Cr the other way round
    input      [12:0] x,
    input      [11:0] y,
    output reg        ev = 1'b0,
    output reg        ev_first = 1'b0,
    output reg [23:0] rgb
);
    localparam LAT = 10;

    // ---- the output's side: the events ----
    reg [9:0]  line = 10'd0;
    always @(posedge clk) if (ce) begin
        if (x == 13'd0 && y == VT - FIRST) begin
            ev_first <= 1'b1;
            line <= 10'd0;
            ev <= !ev;
        end else if (x == 13'd0 && y != 12'd0 && y < H) begin
            ev_first <= 1'b0;
            line <= y[9:0];
            ev <= !ev;
        end
    end

    // ---- the DDR3's side: the row being read, from the event ----
    reg        e0 = 1'b0, e1 = 1'b0, e2 = 1'b0;
    reg [9:0]  row = 10'd0;
    always @(posedge w_clk) begin
        e0 <= ev;
        e1 <= e0;
        e2 <= e1;
        if (e1 != e2)
            row <= line;
        goal <= row + 10'd3;
        hold <= emitted - row > 10'd2;
    end

    // ---- the store, and its read-out: 1 the address, 2 the four lines' words, 3 the row's ----
    reg [9:0]  ra;
    reg [1:0]  sl1, sl2;
    reg [10:0] x1, x2, x3;
    reg [31:0] sq [0:3] /* synthesis syn_ramstyle = "registers" */;
    reg [31:0] w;
    genvar k;
    generate
        for (k = 0; k < 4; k = k + 1) begin : g_st
            reg [31:0] mem [0:1023];
            wire        wen = r_we && (r_slot_d == k || r_slot_i == k);
            wire [31:0] wd = r_slot_d == k ? r_wd_d : r_wd_i;
            always @(posedge w_clk)
                if (wen)
                    mem[r_wa] <= wd;
            always @(posedge clk) if (ce)
                sq[k] <= mem[ra];
        end
    endgenerate
    always @(posedge clk) if (ce) begin
        ra <= x[10:1];
        sl1 <= y[1:0];
        x1 <= x[10:0];
        sl2 <= sl1;
        x2 <= x1;
        w <= sq[sl2];
        x3 <= x2;
    end

    // 4: the pixel two before the one whose word is here (x3: its column), 4:4:4
    function [7:0] mean(input [7:0] a, input [7:0] b);
        reg [8:0] t;
        begin
            t = {1'b0, a} + {1'b0, b} + 9'd1;
            mean = t[8:1];
        end
    endfunction
    reg [31:0] prev;
    reg [7:0]  py, pcb, pcr;
    always @(posedge clk) if (ce) begin
        if (x3[0])
            prev <= w;
        if (!x3[0]) begin
            py <= prev[23:16];
            pcb <= prev[31:24];
            pcr <= prev[15:8];
        end else begin
            py <= prev[7:0];
            pcb <= x3 == W + 1 ? prev[31:24] : mean(prev[31:24], w[31:24]);
            pcr <= x3 == W + 1 ? prev[15:8] : mean(prev[15:8], w[15:8]);
        end
    end

    // 5 to 8: R'G'B' (rcas.v's)
    reg signed [9:0]  yv;
    reg signed [8:0]  cbv, crv;
    reg signed [19:0] my, mrv, mgu, mgv, mbu;
    reg signed [19:0] sr, sg, sb;
    function [7:0] clamp(input signed [19:0] v);
        clamp = v[19] ? 8'd0 : |v[18:16] ? 8'hFF : v[15:8];
    endfunction
    always @(posedge clk) if (ce) begin
        yv <= py < 8'd16 ? 10'sd0 : $signed({2'b00, py}) - 10'sd16;
        cbv <= $signed({1'b0, swap ? pcr : pcb}) - 9'sd128;
        crv <= $signed({1'b0, swap ? pcb : pcr}) - 9'sd128;
        my <= yv * 11'sd298 + 20'sd128;
        mrv <= crv * 11'sd409;
        mgu <= cbv * 11'sd100;
        mgv <= crv * 11'sd208;
        mbu <= cbv * 11'sd516;
        sr <= my + mrv;
        sg <= my - mgu - mgv;
        sb <= my + mbu;
        rgb <= {clamp(sr), clamp(sg), clamp(sb)};
    end
endmodule
