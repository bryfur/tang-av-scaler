// hdmi_scr.v: one TMDS channel's characters made ready for the encoder (tmds.v), N a clock: HDMI's
// framing and, above 340 MHz, HDMI 2.0's scrambling.
//
//   frame     the video guard band sent (the bytes below as data); else DVI: control to the pixel
//   scramble  characters scrambled: HDMI 2.0 6.1.2, here as its inventors' and implementers' patents
//             give it (the specification itself is for adopters):
//
// - An LFSR a channel, G(x) = 1 + x^11 + x^12 + x^13 + x^16, seeds 0xFFFF, 0xFFFE, 0xFFFD for channels
//   0, 1, 2, stepped eight places a character: a 16-bit register shifted up, 0x3801 XORed in when a
//   one falls out [US 11,962,847: the polynomial, the seeds, and its FIG. 2's first 21 values of
//   each channel, which this form gives: sim/scr_tb.py].
// - Once a frame eight characters of ordinary control tokens on all three channels (ucc), after
//   which the LFSRs start again: the first character after them takes the seed [US 11,962,847].
// - Picture bytes and guard band bytes XOR eight bits of the LFSR, then the ordinary encoder
//   [US 9,262,988; US 2014/0340579].  The video guard band as bytes: 0xAB on channels 0 and 2, 0x55
//   on 1 (what HDMI 1.4's guard band characters are of the encoder from a count of zero).
// - Any other control character: its two control bits and the channel's number (00, 01, 10) make
//   four bits, XORed with four of the LFSR's (its bits 11 to 14); with a bit that alternates from one
//   control character to the next (IToggle, the low bit; here 0 after the unscrambled characters)
//   they pick one of 32 ten-bit codes
//   [US 9,262,988 FIG. 4, FIG. 5; US 11,165,539: the alternation, the codes' counts of ones and
//   transitions, which the table below has].
//
// What those texts do not give, chosen here by opt and tried against a sink:
//   opt[1:0]  the LFSR's bits for a byte's bits 7:0: 0 its bits 7:0, 1 its bits 15:8, 2 bits 0:7,
//             3 bits 8:15
//   opt[2]    the control bits' four of the LFSR: 0 vector bit i with LFSR bit 14 - i, 1 with 11 + i
//   opt[3]    the vector: 0 {control 1, control 0, channel}, 1 {channel, control 1, control 0}
//
// Two clocks from input to output.

module hdmi_scr #(parameter N = 1, parameter CH = 0) (
    input                     clk,
    input                     ce,            // a pixel's clock (0: everything here stays as it is)
    input                     frame,
    input                     scramble,
    input      [3:0]          opt,
    input      [8 * N - 1:0]  d,
    input      [2 * N - 1:0]  c,
    input      [N - 1:0]      de,
    input      [N - 1:0]      gb,
    input      [N - 1:0]      ucc,
    output reg [8 * N - 1:0]  d_o,
    output reg [N - 1:0]      de_o,
    output reg [10 * N - 1:0] tok
);
    localparam [15:0] SEED = 16'hFFFF - CH;
    localparam [7:0]  GB = CH == 1 ? 8'h55 : 8'hAB;
    localparam [1:0]  LN = CH;

    function [15:0] step8(input [15:0] v);
        integer i;
        begin
            step8 = v;
            for (i = 0; i < 8; i = i + 1)
                step8 = {step8[14:0], 1'b0} ^ (step8[15] ? 16'h3801 : 16'h0000);
        end
    endfunction
    function [9:0] token(input [1:0] v);            // DVI's and HDMI 1.4's control characters
        case (v)
            2'b00: token = 10'b1101010100;
            2'b01: token = 10'b0010101011;
            2'b10: token = 10'b0101010100;
            default: token = 10'b1010101011;
        endcase
    endfunction
    function [9:0] code(input [4:0] v);             // the scrambled control codes [US 9,262,988 FIG. 5]
        reg [9:0] e;
        begin
            case (v[4:1])
                4'd0: e = 10'b0000010111;
                4'd1: e = 10'b0000011011;
                4'd2: e = 10'b0000011101;
                4'd3: e = 10'b0000011110;
                4'd4: e = 10'b0000100111;
                4'd5: e = 10'b0000110011;
                4'd6: e = 10'b0000111001;
                4'd7: e = 10'b0000111100;
                4'd8: e = 10'b0001000111;
                4'd9: e = 10'b0001100011;
                4'd10: e = 10'b0001110001;
                4'd11: e = 10'b0001111000;
                4'd12: e = 10'b0010000111;
                4'd13: e = 10'b0011000011;
                4'd14: e = 10'b0011100001;
                default: e = 10'b0011110000;
            endcase
            code = v[0] ? ~e : e;
        end
    endfunction

    // the settings, here (they do not change while a picture is sent)
    reg       frame_q, scr_q;
    reg [3:0] opt_q;
    always @(posedge clk) if (ce) begin
        frame_q <= frame;
        scr_q <= scramble;
        opt_q <= opt;
    end

    // stage 1: the LFSR's value for each of the clock's characters; the inputs kept beside them
    reg [15:0]        lfsr = SEED;
    reg [16 * N - 1:0] lq;
    reg [8 * N - 1:0] d_q;
    reg [2 * N - 1:0] c_q;
    reg [N - 1:0]     de_q, gb_q, ucc_q;
    integer           k;
    reg [15:0]        v;
    always @(posedge clk) if (ce) begin
        v = lfsr;
        for (k = 0; k < N; k = k + 1) begin
            lq[16 * k +: 16] <= v;
            v = step8(v);
        end
        lfsr <= ucc[N - 1] ? SEED : v;              // (the unscrambled characters end with a clock)
        d_q <= d;
        c_q <= c;
        de_q <= de;
        gb_q <= gb;
        ucc_q <= ucc;
    end

    // stage 2
    reg        itoggle = 1'b0;
    reg        t;
    reg [15:0] q;
    reg [7:0]  mask;
    reg [3:0]  cv, cm;
    reg        is_data;
    always @(posedge clk) if (ce) begin
        t = itoggle;
        for (k = 0; k < N; k = k + 1) begin
            q = lq[16 * k +: 16];
            case (opt_q[1:0])
                2'd0: mask = q[7:0];
                2'd1: mask = q[15:8];
                2'd2: mask = {q[0], q[1], q[2], q[3], q[4], q[5], q[6], q[7]};
                default: mask = {q[8], q[9], q[10], q[11], q[12], q[13], q[14], q[15]};
            endcase
            cv = opt_q[3] ? {LN, c_q[2 * k +: 2]} : {c_q[2 * k +: 2], LN};
            cm = opt_q[2] ? q[14:11] : {q[11], q[12], q[13], q[14]};
            is_data = de_q[k] || (frame_q && gb_q[k]);
            de_o[k] <= is_data;
            d_o[8 * k +: 8] <= (de_q[k] ? d_q[8 * k +: 8] : GB) ^ (scr_q ? mask : 8'h00);
            if (!scr_q || ucc_q[k]) begin
                tok[10 * k +: 10] <= token(c_q[2 * k +: 2]);
                t = 1'b0;                           // (the alternation starts again with the LFSR)
            end else begin
                tok[10 * k +: 10] <= code({cv ^ cm, t});
                if (!is_data)
                    t = ~t;
            end
        end
        itoggle <= t;
    end
endmodule
