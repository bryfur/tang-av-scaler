// fmeter.v: a clock's frequency against the system clock: its edges, in sixteens, counted over
// 2^25 system clocks.  At 50 MHz one count is 23.84 Hz (hz = count * 16 * 50e6 / 2^25); clocks
// up to 16 x 25 MHz.  tick: a pulse each 2^25 system clocks, shared.

module fmeter (
    input             clk,
    input             tick,
    input             f,
    output reg [31:0] count = 32'd0
);
    reg [3:0] pre = 4'd0;
    always @(posedge f)
        pre <= pre + 4'd1;
    reg [2:0]  s = 3'd0;
    reg [31:0] run = 32'd0;
    always @(posedge clk) begin
        s <= {s[1:0], pre[3]};
        if (tick) begin
            count <= run;
            run <= 32'd0;
        end else if (s[2:1] == 2'b01)
            run <= run + 32'd1;
    end
endmodule
