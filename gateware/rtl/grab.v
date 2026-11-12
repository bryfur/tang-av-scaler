// grab.v: the picture as it leaves for the encoders, for the host to look at with no display: when
// arm changes, eight rows of the next frame (row, row + step, ...; rows counted from the first after
// VSYNC, columns from the row's first pixel, 2048 at most) go to a RAM, 24 bits a pixel; done says
// they are in.  The host reads the RAM by rclk: ra = {which of the eight, column}.

module grab (
    input             clk,
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
    reg [23:0] mem [0:16383];
    reg        de_q, vs_q, a0, a1, a2, armed = 1'b0, live = 1'b0;
    reg [10:0] x, y, want;
    reg [3:0]  k;
    reg [23:0] d_q;
    wire       hit = de && y == want && live && !k[3];
    always @(posedge clk) begin
        de_q <= de;
        vs_q <= vs;
        d_q <= rgb;
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
        end else if (live && de_q && !de) begin
            if (y == want) begin
                k <= k + 4'd1;
                want <= want + {7'd0, step};
            end
            if (k[3] || y == 11'd1079 || (y == want && k == 4'd7)) begin
                live <= 1'b0;
                done <= 1'b1;
            end
        end
        if (hit)
            mem[{k[2:0], x}] <= rgb;
    end
    always @(posedge rclk)
        rd <= mem[ra];
endmodule
