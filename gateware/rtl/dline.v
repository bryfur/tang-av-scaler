// dline.v: a delay of D clocks (4 to 4096) in a block RAM.
module dline #(
    parameter W = 8,
    parameter D = 2200
) (
    input              clk,
    input      [W - 1:0] d,
    output reg [W - 1:0] q
);
    reg [W - 1:0] mem [0:4095];
    reg [11:0]    wa = 12'd0;
    reg [11:0]    ra = 12'd0;
    reg [W - 1:0] q1;
    always @(posedge clk) begin
        wa <= wa + 12'd1;
        ra <= wa - (D - 3);             // (written at wa; read into q1 at ra, a clock after ra is set)
        mem[wa] <= d;
        q1 <= mem[ra];
        q <= q1;
    end
endmodule
