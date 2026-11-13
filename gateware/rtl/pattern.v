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
    input                      ce,            // a pixel's clock (0: everything here stays as it is)
    input                      hd,      // 1280 x 720 [VIC 4: 1650 x 750] for the parameters' picture (PPC 1; set while nothing is shown)
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
    // (the picture's numbers: the parameters', or 1280 x 720's)
    wire [12:0] ha = hd ? 13'd1280 : HA, hf = hd ? 13'd110 : HF, hsw = hd ? 13'd40 : HS, ht = hd ? 13'd1650 : HT;
    wire [11:0] va = hd ? 12'd720 : VA, vf = hd ? 12'd5 : VF, vsw = hd ? 12'd5 : VS, vt = hd ? 12'd750 : VT;
    wire [12:0] BAR = hd ? 13'd160 : HA / 8, BOX = hd ? 13'd80 : HA / 16, STEP = hd ? 13'd3 : HA / 480;

    reg [12:0] x = 13'd0;               // the clock's first pixel
    reg [11:0] y = 12'd0;
    reg [12:0] box = 13'd0;
    wire       eol = x == ht - PPC;
    always @(posedge clk) if (ce) begin
        x <= eol ? 13'd0 : x + PPC[12:0];
        if (eol) begin
            y <= y == vt - 12'd1 ? 12'd0 : y + 12'd1;
            if (y == vt - 12'd1)
                box <= box >= ha - BOX - STEP ? 13'd0 : box + STEP;
        end
    end

    // of the row: is the next one picture; where VSYNC is (rows begin at the picture's first pixel,
    // VSYNC turns HA + HF into its rows)
    reg next_act, vs_first, vs_row, vs_last;
    reg row_act, row_edge, row_box, row_ramp;       // (the test picture's rows, likewise ahead)
    reg [12:0] box_end;
    always @(posedge clk) if (ce) begin
        row_act <= y < va;
        row_edge <= y == 0 || y == va - 12'd1;
        row_box <= y >= va[11:1] - BOX[12:1] && y < va[11:1] + BOX[12:1];
        row_ramp <= y >= va - va[11:3];
        box_end <= box + BOX;
        next_act <= y == vt - 12'd1 || y < va - 12'd1;
        vs_first <= y == va + vf - 12'd1;
        vs_row <= y >= va + vf && y < va + vf + vsw - 12'd1;
        vs_last <= y == va + vf + vsw - 12'd1;
    end

    integer    k;
    reg [12:0] px;
    reg [2:0]  bar, rgb;
    reg [7:0]  grey;
    reg [12:0] x_q;
    reg [11:0] y_q;
    always @(posedge clk) if (ce) begin
        x_q <= x;
        y_q <= y;
        ox <= x_q;
        oy <= y_q;
        for (k = 0; k < PPC; k = k + 1) begin
            px = x_q + k[12:0];
            de[k] <= px < ha && row_act;
            hs[k] <= px >= ha + hf && px < ha + hf + hsw;
            vs[k] <= vs_row || (vs_first && px >= ha + hf) || (vs_last && px < ha + hf);
            pre[k] <= next_act && px >= ht - 13'd10 && px < ht - 13'd2;
            gb[k] <= next_act && px >= ht - 13'd2;
            ucc[k] <= vs_first && px >= ha + hf && px < ha + hf + 13'd8;
            bar = (px >= BAR) + (px >= {BAR, 1'b0}) + (px >= BAR + {BAR, 1'b0}) + (px >= {BAR, 2'b00}) + (px >= BAR + {BAR, 2'b00}) +
                  (px >= {BAR, 1'b0} + {BAR, 2'b00}) + (px >= {BAR, 3'b000} - BAR);
            rgb = ~bar;                 // {g, r, b}: white yellow cyan green magenta red blue black
            grey = HA > 2048 ? px[11:4] : px[10:3];
            if (px == 0 || px == ha - 13'd1 || row_edge || (px >= box && px < box_end && row_box)) begin
                r[8 * k +: 8] <= 8'hFF; g[8 * k +: 8] <= 8'hFF; b[8 * k +: 8] <= 8'hFF;
            end else if (row_ramp) begin
                r[8 * k +: 8] <= grey; g[8 * k +: 8] <= grey; b[8 * k +: 8] <= grey;
            end else begin
                g[8 * k +: 8] <= rgb[2] ? 8'd191 : 8'd0;
                r[8 * k +: 8] <= rgb[1] ? 8'd191 : 8'd0;
                b[8 * k +: 8] <= rgb[0] ? 8'd191 : 8'd0;
            end
        end
    end
endmodule
