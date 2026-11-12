// border.v: where the picture is in the fields as they are captured (vcap.v's words): a game's
// picture is often less than the 720 x 240 of a field, black round it.  Kept since the last clear:
// the first and last word (pair of pixels) and the first and last line of a field that had picture:
// four words in a row with both lumas above thr.  They only grow: a dark scene takes nothing away.
//
// For the host (another clock: they change seldom; read twice): any: there was picture at all.

module border (
    input             llc,
    input             we,
    input      [9:0]  w_ln,
    input      [8:0]  w_col,
    input      [31:0] wd,               // {Cb, Y0, Cr, Y1}
    input      [7:0]  thr,
    input             clr,              // changes: start again
    output reg        any = 1'b0,
    output reg [8:0]  x_min = 9'd511,
    output reg [8:0]  x_max = 9'd0,
    output reg [9:0]  ln_min = 10'd1023,
    output reg [9:0]  ln_max = 10'd0
);
    reg        c0, c1, c2;
    reg [2:0]  run = 3'd0;              // lit words in a row up to this one (to 4)
    reg        q_v = 1'b0, q_lit;
    reg [9:0]  q_ln;
    reg [8:0]  q_col;
    always @(posedge llc) begin
        c0 <= clr;
        c1 <= c0;
        c2 <= c1;
        q_v <= we;
        q_lit <= wd[23:16] > thr && wd[7:0] > thr;
        q_ln <= w_ln;
        q_col <= w_col;
        if (q_v) begin
            // (a line's first word starts the count again)
            run <= !q_lit ? 3'd0 : q_col == 9'd0 ? 3'd1 : run == 3'd4 ? 3'd4 : run + 3'd1;
            if (q_lit && q_col != 9'd0 && run >= 3'd3) begin
                any <= 1'b1;
                if (q_col - 9'd3 < x_min)
                    x_min <= q_col - 9'd3;
                if (q_col > x_max)
                    x_max <= q_col;
                if (q_ln < ln_min)
                    ln_min <= q_ln;
                if (q_ln > ln_max)
                    ln_max <= q_ln;
            end
        end
        if (c1 != c2) begin
            any <= 1'b0;
            x_min <= 9'd511;
            x_max <= 9'd0;
            ln_min <= 10'd1023;
            ln_max <= 10'd0;
            run <= 3'd0;
        end
    end
endmodule
