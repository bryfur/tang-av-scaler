// vcap.v: the ADV7181D's pixel port as it leaves the standard definition core: 8-bit ITU-R BT.656 on
// the Y pins, 27 MHz (LLC), the syncs in the stream (FF 00 00 XY: XY bit 6 F the field, 5 V
// vertical blanking, 4 H: 1 the end of a line's picture (EAV), 0 its start (SAV)); a line's picture
// is Cb Y Cr Y ..., 720 Y.
//
// wide: the pixel port as the CP core drives it (component video): 16 bits, Y on the Y pins and
// Cb, Cr in turn on the C pins, a Y sample a clock (13.5 MHz for 480i), the same sync codes on both.
//
// A field goes to the frame store as it comes, 360 words a line, {Cb, Y0, Cr, Y1}, line n of the
// field at 360 n (the field's lines counted from the end of its vertical blanking): LINES at most.
//
// For the host: pix, the Y samples of the last line; lines, the lines of picture in the last field;
// field, its F; fields, a count of them.  And raw: 1024 samples of all the pins, taken when arm
// changes: from then on (mode 0), from the next sync code (1: the first sample is its XY), from the
// next start of a line of picture (2).

module vcap #(
    parameter LINES = 244
) (
    input             llc,
    input      [7:0]  y,
    input      [7:0]  c,
    input             hs,
    input             vs,
    input             de,
    input             freeze,           // the store is left as it is
    input             wide,
    output reg        we,
    output reg [16:0] wa,
    output reg [31:0] wd,
    output reg        f_we,             // at a line's start: the field (F) the store's line f_wa is of
    output reg [7:0]  f_wa,
    output reg        f_wd,
    output reg [10:0] pix,
    output reg [9:0]  lines,
    output reg        field,
    output reg [15:0] fields = 16'd0,
    input             arm,
    input      [1:0]  mode,
    output reg        done,
    input             rclk,
    input      [9:0]  ra,
    output reg [18:0] rd
);
    reg [18:0] s0, s;                   // {de, vs, hs, c, y}
    reg [7:0]  p1, p2, p3;
    always @(posedge llc) begin
        s0 <= {de, vs, hs, c, y};
        s <= s0;
        p1 <= s[7:0];
        p2 <= p1;
        p3 <= p2;
    end
    wire [7:0] b = s[7:0];
    wire       trs = p3 == 8'hFF && p2 == 8'h00 && p1 == 8'h00;

    reg        v = 1'b1, in_line = 1'b0;
    reg [1:0]  ph;
    reg [8:0]  col;
    reg [10:0] n;
    reg [9:0]  ln;
    reg [16:0] base;
    reg [7:0]  cb, y0, cr;
    reg        frz_s0, frz, wide_s0, wd16;
    always @(posedge llc) begin
        frz_s0 <= freeze;
        frz <= frz_s0;
        wide_s0 <= wide;
        wd16 <= wide_s0;
        we <= 1'b0;
        f_we <= 1'b0;
        if (trs) begin
            v <= b[5];
            if (!b[4]) begin                        // SAV
                f_we <= !b[5] && !frz && ln < LINES;
                f_wa <= ln[7:0];
                f_wd <= b[6];
                in_line <= !b[5];
                ph <= 2'd0;
                col <= 9'd0;
                n <= 11'd0;
            end else begin                          // EAV
                if (in_line) begin
                    pix <= n - (wd16 ? 11'd3 : 11'd1);  // (less those counted in the sync code)
                    ln <= ln + 10'd1;
                    base <= base + 17'd360;
                end
                in_line <= 1'b0;
                if (b[5] && !v) begin               // the field's picture is over
                    lines <= ln + (in_line ? 10'd1 : 10'd0);
                    field <= b[6];
                    fields <= fields + 16'd1;
                end
                if (b[5] && !in_line) begin
                    ln <= 10'd0;
                    base <= 17'd0;
                end
            end
        end else if (in_line && wd16) begin
            ph <= {1'b0, !ph[0]};
            if (!ph[0]) begin
                cb <= s[15:8];
                y0 <= b;
            end else begin
                wd <= {cb, y0, s[15:8], b};
                wa <= base + {8'd0, col};
                we <= !frz && col < 9'd360 && ln < LINES;
                col <= col + 9'd1;
            end
            if (!(&n))
                n <= n + 11'd1;
        end else if (in_line) begin
            ph <= ph + 2'd1;
            case (ph)
                2'd0: cb <= b;
                2'd1: y0 <= b;
                2'd2: cr <= b;
                2'd3: begin
                    wd <= {cb, y0, cr, b};
                    wa <= base + {8'd0, col};
                    we <= !frz && col < 9'd360 && ln < LINES;
                    col <= col + 9'd1;
                end
            endcase
            if (ph[0] && !(&n))
                n <= n + 11'd1;
        end
    end

    // the raw capture
    reg [18:0] raw [0:1023];
    reg        arm_s0, arm_s1, arm_s2, waiting = 1'b0, taking = 1'b0;
    reg [9:0]  wi;
    wire       go = mode == 2'd0 || (trs && (mode == 2'd1 || (!b[4] && !b[5])));
    always @(posedge llc) begin
        arm_s0 <= arm;
        arm_s1 <= arm_s0;
        arm_s2 <= arm_s1;
        if (arm_s1 != arm_s2) begin
            waiting <= 1'b1;
            taking <= 1'b0;
            done <= 1'b0;
        end else if (waiting && go) begin
            waiting <= 1'b0;
            taking <= 1'b1;
            wi <= 10'd1;
        end else if (taking) begin
            wi <= wi + 10'd1;
            if (&wi) begin
                taking <= 1'b0;
                done <= 1'b1;
            end
        end
        if ((waiting && go) || taking)
            raw[waiting ? 10'd0 : wi] <= s;
    end
    always @(posedge rclk)
        rd <= raw[ra];
endmodule
