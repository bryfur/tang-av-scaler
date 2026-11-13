// grab.v: the picture as it leaves for the encoders, for the host to look at with no display: when
// arm changes, 2^LR rows of the next frame (row, row + step, ...; rows counted from the first after
// VSYNC, columns from the row's first pixel, 2048 at most) go to a RAM, 24 bits a pixel; done says
// they are in.  The host reads the RAM by rclk: ra = {which of the rows (3 bits), column}.
// (Two rows a frame: 6 block RAMs.  Eight were 24, a fourteenth of the chip's, for a picture taken
// a few seconds sooner: a whole frame is 540 frames' rows, 9 s of waiting, and the reading the rest.)

module grab #(
    parameter LR = 1
) (
    input             clk,
    input             ce,            // a pixel's clock (0: everything here stays as it is)
    input             de,
    input             vs,
    input      [23:0] rgb,
    input      [10:0] row,
    input      [3:0]  step,
    input             arm,
    output reg        done = 1'b0,
    input             rclk,
    input      [13:0] ra,
    output reg [23:0] rd
);
    reg [23:0] mem [0:(2048 << LR) - 1];
    reg        de_q, vs_q, a0, a1, a2, armed = 1'b0, live = 1'b0;
    reg [10:0] x, y, want;
    reg [3:0]  k;
    reg [23:0] d_q;
    reg        yeq;
    wire       hit = de && yeq && live && k < (4'd1 << LR);
    always @(posedge clk) if (ce) begin
        de_q <= de;
        vs_q <= vs;
        d_q <= rgb;
        yeq <= y == want;
        a0 <= arm;
        a1 <= a0;
        a2 <= a1;
        x <= de ? x + 11'd1 : 11'd0;
        if (vs && !vs_q)
            y <= 11'd0;
        else if (de_q && !de)
            y <= y + 11'd1;
        if (a1 != a2) begin
            armed <= 1'b1;
            live <= 1'b0;
            done <= 1'b0;
        end else if (armed && vs && !vs_q) begin
            armed <= 1'b0;
            live <= 1'b1;
            k <= 4'd0;
            want <= row;
        end else if (live && vs && !vs_q) begin
            // (the frame is over: rows asked for past its last, or a frame of fewer than 1080: 720p)
            live <= 1'b0;
            done <= 1'b1;
        end else if (live && de_q && !de) begin
            if (yeq) begin
                k <= k + 4'd1;
                want <= want + {7'd0, step};
            end
            if (k >= (4'd1 << LR) || y == 11'd1079 || (yeq && k == (4'd1 << LR) - 4'd1)) begin
                live <= 1'b0;
                done <= 1'b1;
            end
        end
        if (hit)
            mem[{k[LR - 1:0], x}] <= rgb;
    end
    always @(posedge rclk)
        rd <= mem[{ra[11 + LR - 1:11], ra[10:0]}];
endmodule
