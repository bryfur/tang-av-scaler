// hdmi_audio.v: HDMI's data islands [HDMI 1.4 5.2.3, 5.3]: one packet in each line's back porch,
// when there is one to send: the sound's samples (two channels of L-PCM, as they come from
// audio_in.v), the audio clock's N and CTS, the audio and the AVI InfoFrames.  One pixel a clock.
//
// A line, from the character after HSYNC's end (the back porch is 148 characters at 1080p):
//   0-11    control
//   12-19   the data island's preamble (CTL0 and CTL2: pre)
//   20-21   guard band
//   22-53   the packet: 32 characters; channel 0 carries {not the first, a header bit, VSYNC,
//           HSYNC}, channels 1 and 2 the four subpackets' even and odd bits, all as TERC4
//   54-55   guard band
// then control until the video's own preamble.  act with the 36 characters 20-55, k0, k1, k2 their
// ten bits (to the encoders in the control tokens' place; q[0] goes first).
//
// The packets, by the line (counted from VSYNC's start): line 2 the AVI InfoFrame (RGB, full range,
// 16:9, VIC 16), line 4 the audio InfoFrame (two channels, the rest as the stream says), every 32nd
// line N and CTS, else the samples waiting (two at most in a packet).
//
// The sound: fs is 48 kHz, its clock from the PLL the pixel clock comes from (audio_in.v; the CPU
// sets the MS5351M's dividers: sw/board.c), so 128 fs = pixel clock x N / CTS holds exactly with
// N = 6144 and CTS = 148352 at 148.5 / 1.001 MHz, or 148500 at 148.5 MHz (cts_alt).  The channel
// status says 48 kHz, 24 bits.
//
// s_tick changes with each new pair s_l, s_r (the 24-bit samples; from another clock: they stay
// as they are for a sample's time).

module hdmi_audio (
    input             clk,
    input             ce,            // a pixel's clock (0: everything here stays as it is)
    input             en,
    input             hs,
    input             vs,
    input             cts_alt,
    input             hd,               // 1280 x 720 [VIC 4], the pixel clock a half (CTS a half)
    input             s_tick,
    input      [23:0] s_l,
    input      [23:0] s_r,
    output reg        pre = 1'b0,
    output reg        act = 1'b0,
    output reg [9:0]  k0,
    output reg [9:0]  k1,
    output reg [9:0]  k2
);
    localparam [19:0] N = 20'd6144;
    wire [19:0] CTS0 = cts_alt ? 20'd148500 : 20'd148352;
    wire [19:0] CTS = hd ? {1'b0, CTS0[19:1]} : CTS0;
    // the channel status [IEC 60958-3]: consumer, PCM, copying allowed; 48 kHz; 24 bits
    localparam [39:0] CS = 40'h0B_02_00_00_04;
    // the InfoFrames' bytes [CEA-861-D]: PB0 the checksum (the header's and the bytes' sum zero)
    localparam [7:0] AVI1 = 8'h10, AVI2 = 8'h28, AVI3 = 8'h08;
    wire [7:0] AVI4 = hd ? 8'h04 : 8'h10;
    wire [7:0] AVI0 = 8'h00 - (8'h82 + 8'h02 + 8'h0D + AVI1 + AVI2 + AVI3 + AVI4);
    localparam [7:0] AIF0 = 8'h00 - (8'h84 + 8'h01 + 8'h0A + 8'h01);

    function [9:0] terc4(input [3:0] v);
        case (v)
            4'h0: terc4 = 10'b1010011100;
            4'h1: terc4 = 10'b1001100011;
            4'h2: terc4 = 10'b1011100100;
            4'h3: terc4 = 10'b1011100010;
            4'h4: terc4 = 10'b0101110001;
            4'h5: terc4 = 10'b0100011110;
            4'h6: terc4 = 10'b0110001110;
            4'h7: terc4 = 10'b0100111100;
            4'h8: terc4 = 10'b1011001100;
            4'h9: terc4 = 10'b0100111001;
            4'hA: terc4 = 10'b0110011100;
            4'hB: terc4 = 10'b1011000110;
            4'hC: terc4 = 10'b1010001110;
            4'hD: terc4 = 10'b1001110001;
            4'hE: terc4 = 10'b0101100011;
            default: terc4 = 10'b1011000011;
        endcase
    endfunction
    // the error correction's eight bits [HDMI 1.4 5.2.3.5: 1 + x^6 + x^7 + x^8], over n bits, the
    // lowest first
    function [7:0] ecc(input [7:0] from, input [23:0] d, input integer n);
        integer i;
        begin
            ecc = from;
            for (i = 0; i < n; i = i + 1)
                ecc = (ecc >> 1) ^ ((ecc[0] ^ d[i]) ? 8'h83 : 8'h00);
        end
    endfunction

    // the samples waiting (four at most), each with its place in the 192 of a block
    reg        t0, t1, t2;
    reg [23:0] fl [0:3], fr [0:3];
    reg [7:0]  fn [0:3];
    reg [1:0]  wp = 2'd0, rp = 2'd0;
    reg [2:0]  cnt = 3'd0;
    reg [7:0]  frame = 8'd0;
    reg [1:0]  take = 2'd0;             // taken into this line's packet
    reg        take_s = 1'b0;

    // the line: its characters from HSYNC's end, its number from VSYNC's start
    reg        hs_q, vs_q, hs_q2, vs_q2;        // (hs, vs come out of a block RAM: a register first)
    reg [7:0]  x = 8'd255;
    reg [10:0] line = 11'd0;
    reg [2:0]  kind;                    // this line's packet: 0 none, 1 AVI, 2 audio InfoFrame, 3 N/CTS, 4 samples
    reg        k_avi, k_aif, k_ncts, k_smp;     // (which it is, a clock after kind: for its bytes)
    reg [23:0] hb;
    reg [55:0] sp [0:3];
    reg [31:0] hdr;
    reg [63:0] sub [0:3];
    reg [7:0]  e1 [0:3];
    reg [7:0]  he;
    reg [55:0] spq [0:3];
    reg [3:0]  ph = 4'd0;
    // (the next clock's place in the line, for what is wide: the subpackets kept and shifted)
    wire [7:0] xn = hs_q2 && !hs_q ? 8'd0 : x != 8'd255 ? x + 8'd1 : x;
    reg        x_keep = 1'b0, x_shift = 1'b0;
    // (the two samples at the front: a clock late, but they wait there since before the line's start)
    reg [23:0] al, ar, bl, br;
    reg [7:0]  an, bn;
    function [7:0] status(input [23:0] l, input [23:0] r, input [7:0] n);   // {P C U V of right, of left}
        reg c;
        begin
            c = n < 8'd40 ? CS[n] : 1'b0;
            status = {^r ^ c, c, 2'b00, ^l ^ c, c, 2'b00};
        end
    endfunction
    integer    i;
    always @(posedge clk) if (ce) begin
        t0 <= s_tick;
        t1 <= t0;
        t2 <= t1;
        hs_q <= hs;
        vs_q <= vs;
        hs_q2 <= hs_q;
        vs_q2 <= vs_q;
        take_s <= 1'b0;
        k_avi <= kind == 3'd1;
        k_aif <= kind == 3'd2;
        k_ncts <= kind == 3'd3;
        k_smp <= kind == 3'd4;
        {al, ar, an} <= {fl[rp], fr[rp], fn[rp]};
        {bl, br, bn} <= {fl[rp + 2'd1], fr[rp + 2'd1], fn[rp + 2'd1]};
        if (t1 != t2 && cnt != 3'd4) begin
            fl[wp] <= s_l;
            fr[wp] <= s_r;
            fn[wp] <= frame;
            wp <= wp + 2'd1;
            frame <= frame == 8'd191 ? 8'd0 : frame + 8'd1;
        end
        cnt <= cnt + (t1 != t2 && cnt != 3'd4 ? 3'd1 : 3'd0) - (take_s ? {1'b0, take} : 3'd0);
        if (take_s)
            rp <= rp + take;

        if (vs_q && !vs_q2)
            line <= 11'd0;
        else if (hs_q2 && !hs_q)
            line <= line + 11'd1;
        if (hs_q2 && !hs_q)
            x <= 8'd0;
        else if (x != 8'd255)
            x <= x + 8'd1;

        // 0: which packet; 2: its bytes; 3 to 9: with their error correction
        if (x == 8'd0) begin
            kind <= !en ? 3'd0 : line == 11'd2 ? 3'd1 : line == 11'd4 ? 3'd2 : line[4:0] == 5'd8 ? 3'd3 :
                    cnt != 3'd0 ? 3'd4 : 3'd0;
            take <= cnt >= 3'd2 ? 2'd2 : cnt[1:0];
        end
        if (x == 8'd2) begin
            for (i = 0; i < 4; i = i + 1)
                sp[i] <= 56'd0;
            if (k_avi) begin
                hb <= {8'h0D, 8'h02, 8'h82};
                sp[0] <= {16'd0, AVI4, AVI3, AVI2, AVI1, AVI0};
            end else if (k_aif) begin
                hb <= {8'h0A, 8'h01, 8'h84};
                sp[0] <= {40'd0, 8'h01, AIF0};
            end else if (k_ncts) begin
                hb <= {8'h00, 8'h00, 8'h01};
                for (i = 0; i < 4; i = i + 1)
                    sp[i] <= {N[7:0], N[15:8], 4'd0, N[19:16], CTS[7:0], CTS[15:8], 4'd0, CTS[19:16], 8'd0};
            end else begin
                // (a sample's block start flag: bit 4 for the first, 5 for the second)
                hb <= {2'b00, take == 2'd2 && bn == 8'd0, an == 8'd0, 4'd0, 6'd0, take == 2'd2, 1'b1, 8'h02};
                sp[0] <= {status(al, ar, an), ar, al};
                if (take == 2'd2)
                    sp[1] <= {status(bl, br, bn), br, bl};
                take_s <= k_smp;
            end
        end
        // (a subpacket's in four clocks, 14 bits each: spq the bits still to go)
        ph <= {ph[2:0], x == 8'd3};
        if (x == 8'd3) begin
            he <= ecc(8'd0, hb, 24);
            for (i = 0; i < 4; i = i + 1) begin
                e1[i] <= 8'd0;
                spq[i] <= sp[i];
            end
        end else if (ph != 4'd0)
            for (i = 0; i < 4; i = i + 1) begin
                e1[i] <= ecc(e1[i], {10'd0, spq[i][13:0]}, 14);
                spq[i] <= {14'd0, spq[i][55:14]};
            end
        x_keep <= xn == 8'd9;
        x_shift <= xn >= 8'd22 && xn < 8'd54;
        if (x_keep) begin
            hdr <= {he, hb};
            for (i = 0; i < 4; i = i + 1)
                sub[i] <= {e1[i], sp[i]};
        end

        // the characters
        pre <= kind != 3'd0 && x >= 8'd12 && x < 8'd20;
        act <= kind != 3'd0 && x >= 8'd20 && x < 8'd56;
        if ((x >= 8'd20 && x < 8'd22) || (x >= 8'd54 && x < 8'd56)) begin
            k0 <= terc4({2'b11, vs_q, hs_q});
            k1 <= 10'b0100110011;
            k2 <= 10'b0100110011;
        end else begin
            k0 <= terc4({x != 8'd22, hdr[0], vs_q, hs_q});
            k1 <= terc4({sub[3][0], sub[2][0], sub[1][0], sub[0][0]});
            k2 <= terc4({sub[3][1], sub[2][1], sub[1][1], sub[0][1]});
        end
        if (x_shift) begin
            hdr <= {1'b0, hdr[31:1]};
            for (i = 0; i < 4; i = i + 1)
                sub[i] <= {2'b00, sub[i][63:2]};
        end
    end
endmodule
