// ddr_model.v: the DDR3 controller's user port (rtl/ddr3/ddr3_top.v) as a memory, for the
// testbenches: a command when cmd_en, ready now and then, a read's line eight clocks later.
// The lines kept: {slot 3, line 10, sixteen pixels' number 7} of cap_ddr.v's address.
module ddr_model (
    input              clk,
    output reg         cmd_ready = 1'b0,
    input      [2:0]   cmd,
    input              cmd_en,
    input      [28:0]  addr,
    input      [255:0] wr_data,
    input              wr_data_en,
    output reg [255:0] rd_data,
    output reg         rd_data_valid = 1'b0
);
    reg [255:0] mem [0:1048575];
    wire [24:0] line = addr[27:3];
    wire [19:0] ix = {line[24:22], line[16:0]};
    reg [255:0] pd [0:7];
    reg [7:0]   pv = 8'd0;
    reg [15:0]  lfsr = 16'hACE1;
    reg         was_ready = 1'b0;
    integer     k;
    always @(posedge clk) begin
        lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
        cmd_ready <= lfsr[0] | lfsr[3];
        was_ready <= cmd_ready;
        if (cmd_en && !was_ready) begin
            $display("ddr_model: a command without ready");
            $finish;
        end
        if (cmd_en && cmd == 3'd0)
            mem[ix] <= wr_data;
        pd[0] <= mem[ix];
        pv <= {pv[6:0], cmd_en && cmd == 3'd1};
        for (k = 1; k < 8; k = k + 1)
            pd[k] <= pd[k - 1];
        rd_data <= pd[7];
        rd_data_valid <= pv[7];
    end
endmodule
