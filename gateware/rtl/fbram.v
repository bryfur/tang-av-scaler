// fbram.v: the frame store: BLOCKS x 1024 words of 32 bits, written on one clock and read on
// another; a block is two block RAMs of 1024 x 16 (a GW5A's 36-bit-wide RAM takes two sites
// anyway).  The read is in steps a 148.5 MHz clock takes: the address (ra) goes to a register a
// block (the RAMs lie all over the chip), each RAM reads, a group's sixteen are chosen from, then
// the groups: rd is the word at ra four clocks before.

module fbram #(
    parameter BLOCKS = 86
) (
    input             wclk,
    input             we,
    input      [16:0] wa,
    input      [31:0] wd,
    input             rclk,
    input      [16:0] ra,
    output reg [31:0] rd
);
    localparam GROUPS = (BLOCKS + 15) / 16;

    reg        we_q;
    reg [16:0] wa_q;
    reg [31:0] wd_q;
    always @(posedge wclk) begin
        we_q <= we;
        wa_q <= wa;
        wd_q <= wd;
    end

    reg [6:0]  sel1, sel2, sel3;        // the address's block, as the read moves on
    always @(posedge rclk) begin
        sel1 <= ra[16:10];
        sel2 <= sel1;
        sel3 <= sel2;
    end

    reg [31:0] gq [0:GROUPS - 1];
    genvar g, k;
    generate
        for (g = 0; g < GROUPS; g = g + 1) begin : g_grp
            wire [31:0] q [0:15];
            for (k = 0; k < 16; k = k + 1) begin : g_blk
                if (g * 16 + k < BLOCKS) begin : g_ram
                    reg [15:0] hi [0:1023];
                    reg [15:0] lo [0:1023];
                    reg [15:0] hi_q, lo_q;
                    reg        wen;
                    reg [9:0]  ra_g /* synthesis syn_preserve = 1 */;
                    always @(posedge rclk)
                        ra_g <= ra[9:0];
                    always @(posedge wclk) begin
                        wen <= we && wa[16:10] == g * 16 + k;
                        if (wen) begin
                            hi[wa_q[9:0]] <= wd_q[31:16];
                            lo[wa_q[9:0]] <= wd_q[15:0];
                        end
                    end
                    always @(posedge rclk) begin
                        hi_q <= hi[ra_g];
                        lo_q <= lo[ra_g];
                    end
                    assign q[k] = {hi_q, lo_q};
                end else begin : g_none
                    assign q[k] = 32'd0;
                end
            end
            always @(posedge rclk)
                gq[g] <= q[sel2[3:0]];
        end
    endgenerate
    always @(posedge rclk)
        rd <= sel3[6:4] < GROUPS ? gq[sel3[6:4]] : 32'd0;
endmodule
