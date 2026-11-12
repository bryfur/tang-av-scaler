// osd.v: text over the picture as it leaves for the encoders: ROWS lines of COLS characters, 16 x
// 32 pixels each (rtl/osd_font.hex: tools/mkfont.py), white on the picture darkened to a quarter,
// from (X0, Y0) of the picture.  The characters are a RAM the register bus writes (wa = line * 64 +
// column; 0 to 31: nothing); what they say is the writer's business (the CPU's program: sw/).
//
// i_t: {de, hs, vs, pre, gb, ucc} of the pixel i_rgb; o_t, o_rgb the same LAT clocks later, with or
// without the text (on).

`ifndef OSD_FONT
`define OSD_FONT "osd_font.hex"
`endif

module osd #(
    parameter X0 = 272,
    parameter Y0 = 40,
    parameter COLS = 48,
    parameter ROWS = 8,
    parameter PAD = 12
) (
    input             clk,
    input             on,
    input      [5:0]  i_t,
    input      [23:0] i_rgb,
    output     [5:0]  o_t,
    output reg [23:0] o_rgb,
    input             wclk,
    input             we,
    input      [8:0]  wa,
    input      [7:0]  wd
);
    localparam LAT = 7;
    localparam W = 16 * COLS, H = 32 * ROWS;
    reg [7:0]  tmem [0:511];
    reg [15:0] font [0:4095];
    initial $readmemh(`OSD_FONT, font);
    always @(posedge wclk)
        if (we)
            tmem[wa] <= wd;

    // the pixel's place: x from the line's first pixel, y from the first line after VSYNC
    wire       de = i_t[5], vs = i_t[3];
    reg        de_q = 1'b0, vs_q = 1'b0, on0 = 1'b0, on1 = 1'b0;
    reg [11:0] x = 12'd0, y = 12'd0;
    // 1: its place in the text; 2: the character's address; 3: the character; 4: its row's address;
    // 5: the row; 6: the pixel; 7: the picture with it
    reg [11:0] dx1, dy1;
    reg        tx1, bx1, tx2, bx2, tx3, bx3, tx4, bx4, tx5, bx5, bx6, px6;
    reg [8:0]  ra;
    reg [3:0]  sx2, sx3, sx4, sx5;
    reg [4:0]  sy2, sy3;
    reg [7:0]  ch;
    reg [11:0] fa;
    reg [15:0] frow;
    reg [29:0] sb [1:LAT] /* synthesis syn_srlstyle = "registers" */;
    integer    i;
    always @(posedge clk) begin
        de_q <= de;
        vs_q <= vs;
        on0 <= on;
        on1 <= on0;
        x <= de ? x + 12'd1 : 12'd0;
        if (vs && !vs_q)
            y <= 12'd0;
        else if (de_q && !de)
            y <= y + 12'd1;

        dx1 <= x - X0;
        dy1 <= y - Y0;
        tx1 <= on1 && de && x >= X0 && x < X0 + W && y >= Y0 && y < Y0 + H;
        bx1 <= on1 && de && x >= X0 - PAD && x < X0 + W + PAD && y >= Y0 - PAD && y < Y0 + H + PAD;

        ra <= {dy1[7:5], dx1[9:4]};
        sx2 <= dx1[3:0];
        sy2 <= dy1[4:0];
        {tx2, bx2} <= {tx1, bx1};

        ch <= tmem[ra];
        {sx3, sy3, tx3, bx3} <= {sx2, sy2, tx2, bx2};

        fa <= {ch[6:0], sy3};
        {sx4, tx4, bx4} <= {sx3, tx3, bx3};

        frow <= font[fa];
        {sx5, tx5, bx5} <= {sx4, tx4, bx4};

        px6 <= tx5 && frow[4'd15 - sx5];
        bx6 <= bx5;

        sb[1] <= {i_t, i_rgb};
        for (i = 2; i <= LAT; i = i + 1)
            sb[i] <= sb[i - 1];
        o_rgb <= px6 ? 24'hF0F0F0 : bx6 ? {2'b00, sb[LAT - 1][23:18], 2'b00, sb[LAT - 1][15:10], 2'b00, sb[LAT - 1][7:2]} :
                 sb[LAT - 1][23:0];
    end
    assign o_t = sb[LAT][29:24];
endmodule
