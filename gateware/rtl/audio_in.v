// audio_in.v: the PCM1808 audio converter (a slave: its three clocks from here), on the MS5351M's
// CLK2 (clk: 148.5 MHz, or that / 1.001):
//
//   SCKI = clk / 12        12.375 MHz: 256 fs, fs = 48.34 kHz
//   BCK  = SCKI / 4        64 fs
//   LRCK = BCK / 64        low: the left channel (I2S)
//
// Its data are taken in the middle of BCK's high half, 32 bits each half of LRCK (the first sent in
// bit 31): l, r, the words as they came, with a change of tick.  The 24-bit sample is bits 30:7
// (I2S: a BCK late) or 31:8 (left justified).

module audio_in (
    input             clk,
    output reg        scki = 1'b0,
    output            bck,
    output            lrck,
    input             dout,
    output reg [31:0] l,
    output reg [31:0] r,
    output reg        tick = 1'b0
);
    reg [3:0]  c12 = 4'd0;
    reg [7:0]  c = 8'd0;                // SCKI periods in a sample
    reg [31:0] sh;
    reg        d0, d1;
    assign bck = c[1];
    assign lrck = c[7];
    always @(posedge clk) begin
        d0 <= dout;
        d1 <= d0;
        c12 <= c12 == 4'd11 ? 4'd0 : c12 + 4'd1;
        scki <= c12 < 4'd6;
        if (c12 == 4'd11)
            c <= c + 8'd1;
        // BCK's high half is SCKI periods 2, 3 of each four: its middle, the end of period 2
        if (c[1:0] == 2'd2 && c12 == 4'd11) begin
            sh <= {sh[30:0], d1};
            if (c[6:2] == 5'd31) begin
                if (c[7]) begin
                    r <= {sh[30:0], d1};
                    tick <= !tick;
                end else
                    l <= {sh[30:0], d1};
            end
        end
    end
endmodule
