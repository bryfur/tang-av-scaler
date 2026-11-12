// pattern.v: video timing and a test picture, PPC pixels a clock (side by side, the first at the
// low end; the line's lengths are multiples of PPC): eight colour bars (75 %), a white line round
// the edge of the frame (the picture's geometry: all four must show), a grey ramp along the bottom
// eighth, a white square that moves.  Syncs positive, VSYNC changing at HSYNC's leading edge
// [CEA-861].  The defaults: 1920x1080p60 [VIC 16: 2200 x 1125, 148.5 MHz]; 3840x2160 [VIC 95, 97:
// 4400 x 2250, 297 MHz at 30 Hz, 594 MHz at 60] is HA 3840, HF 176, HS 88, HT 4400, VA 2160, VF 8,
// VS 10, VT 2250.
//
// With each pixel, HDMI's framing of the blanking before a line of picture [HDMI 1.4 5.2.2]: pre
// the eight characters of the video preamble, gb the two of the video guard band; and ucc, the
// eight characters at VSYNC's leading edge sent unscrambled when the rest is scrambled [HDMI 2.0:
// the scrambler synchronization control period; a whole number of clocks, PPC 4].

module pattern #(
    parameter PPC = 1,
    parameter HA = 1920, HF = 88, HS = 44, HT = 2200,
    parameter VA = 1080, VF = 4, VS = 5, VT = 1125
) (
    input                      clk,
    output reg [PPC - 1:0]     de,
    output reg [PPC - 1:0]     hs,
    output reg [PPC - 1:0]     vs,
    output reg [PPC - 1:0]     pre,
    output reg [PPC - 1:0]     gb,
    output reg [PPC - 1:0]     ucc,
    output reg [8 * PPC - 1:0] r,
    output reg [8 * PPC - 1:0] g,
    output reg [8 * PPC - 1:0] b,
    output reg [12:0]          ox,      // the clock's first pixel as de, r, g, b have it: its column
    output reg [11:0]          oy       // and row (in the picture: below HA, VA)
);
    localparam BAR = HA / 8, BOX = HA / 16, STEP = HA / 480;

    reg [12:0] x = 13'd0;               // the clock's first pixel
    reg [11:0] y = 12'd0;
    reg [12:0] box = 13'd0;
    wire       eol = x == HT - PPC;
    always @(posedge clk) begin
        x <= eol ? 13'd0 : x + PPC[12:0];
        if (eol) begin
            y <= y == VT - 1 ? 12'd0 : y + 12'd1;
            if (y == VT - 1)
                box <= box >= HA - BOX - STEP ? 13'd0 : box + STEP[12:0];
        end
    end

    // of the row: is the next one picture; where VSYNC is (rows begin at the picture's first pixel,
    // VSYNC turns HA + HF into its rows)
    reg next_act, vs_first, vs_row, vs_last;
    always @(posedge clk) begin
        next_act <= y == VT - 1 || y < VA - 1;
        vs_first <= y == VA + VF - 1;
        vs_row <= y >= VA + VF && y < VA + VF + VS - 1;
        vs_last <= y == VA + VF + VS - 1;
    end

    integer    k;
    reg [12:0] px;
    reg [2:0]  bar, rgb;
    reg [7:0]  grey;
    reg [12:0] x_q;
    reg [11:0] y_q;
    always @(posedge clk) begin
        x_q <= x;
        y_q <= y;
        ox <= x_q;
        oy <= y_q;
        for (k = 0; k < PPC; k = k + 1) begin
            px = x_q + k[12:0];
            de[k] <= px < HA && y_q < VA;
            hs[k] <= px >= HA + HF && px < HA + HF + HS;
            vs[k] <= vs_row || (vs_first && px >= HA + HF) || (vs_last && px < HA + HF);
            pre[k] <= next_act && px >= HT - 10 && px < HT - 2;
            gb[k] <= next_act && px >= HT - 2;
            ucc[k] <= vs_first && px >= HA + HF && px < HA + HF + 8;
            bar = (px >= BAR) + (px >= 2 * BAR) + (px >= 3 * BAR) + (px >= 4 * BAR) + (px >= 5 * BAR) +
                  (px >= 6 * BAR) + (px >= 7 * BAR);
            rgb = ~bar;                 // {g, r, b}: white yellow cyan green magenta red blue black
            grey = HA > 2048 ? px[11:4] : px[10:3];
            if (px == 0 || px == HA - 1 || y_q == 0 || y_q == VA - 1 ||
                (px >= box && px < box + BOX && y_q >= VA / 2 - BOX / 2 && y_q < VA / 2 + BOX / 2)) begin
                r[8 * k +: 8] <= 8'hFF; g[8 * k +: 8] <= 8'hFF; b[8 * k +: 8] <= 8'hFF;
            end else if (y_q >= VA - VA / 8) begin
                r[8 * k +: 8] <= grey; g[8 * k +: 8] <= grey; b[8 * k +: 8] <= grey;
            end else begin
                g[8 * k +: 8] <= rgb[2] ? 8'd191 : 8'd0;
                r[8 * k +: 8] <= rgb[1] ? 8'd191 : 8'd0;
                b[8 * k +: 8] <= rgb[0] ? 8'd191 : 8'd0;
            end
        end
    end
endmodule
