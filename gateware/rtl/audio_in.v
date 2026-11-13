// audio_in.v: the PCM1808 audio converter (a slave: its three clocks from here), on the MS5351M's
// CLK2 (clk: 512 fs, 24.576 MHz for 48 kHz; from the PLL the pixel clock comes from, so the sound's
// rate and the picture's keep their ratio: hdmi_audio.v's N and CTS):
//
//   SCKI = clk / 2         256 fs
//   BCK  = SCKI / 4        64 fs
//   LRCK = BCK / 64        low: the left channel (I2S)
//
// Its data are taken in BCK's high half (through two registers: three quarters of the way through
// it), 32 bits each half of LRCK (the first sent in bit 31): l, r, the words as they came, with a
// change of tick.  The 24-bit sample is bits 30:7 (I2S: a BCK late) or 31:8 (left justified).
//
// (Until 2026-11-12 clk was the pixel clock's twin and SCKI clk / 12: fs was 48.3 kHz, 0.6 % above
// 48 kHz.  A display and a capture device took it; an AV receiver showed no sound at all.)

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
    reg [7:0]  c = 8'd0;                // SCKI periods in a sample
    reg [31:0] sh;
    reg        d0, d1;
    assign bck = c[1];
    assign lrck = c[7];
    always @(posedge clk) begin
        d0 <= dout;
        d1 <= d0;
        scki <= !scki;
        if (scki)                       // an SCKI period's end
            c <= c + 8'd1;
        // BCK's high half is SCKI periods 2, 3 of each four
        if (c[1:0] == 2'd3 && scki) begin
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
