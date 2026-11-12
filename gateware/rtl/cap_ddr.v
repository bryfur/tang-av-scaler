// cap_ddr.v: vcap.v's fields into the DDR3.  A line of the DDR3 (256 bits) is sixteen pixels: eight
// of vcap.v's words, the first at the low end; a field has a slot of eight, a slot a bank of the
// memory (its rows stay open as the fields are read side by side):
//
//   the DDR3's line = {slot 3, 5'd0, the field's line 10, the sixteen pixels' number 7}
//
// Fields go to the slots in turn.  When one is all in, on pclk: latest its slot, par[slot] its F,
// nfields how many there have been (to 7), flines its lines.  freeze: the fields in the memory are
// left as they are (a field begun or ended under it is not counted).
//
// And of the field coming in now: prog of its lines are in the memory (prog_slot: its slot): the
// picture can be made from it before it is all there (deint.v's ll).

module cap_ddr (
    input              llc,
    input              we,
    input      [9:0]   w_ln,
    input      [8:0]   w_col,
    input      [31:0]  wd,
    input              eof,
    input              eof_f,
    input      [9:0]   eof_lines,
    input              freeze,

    input              pclk,
    output             a_valid,
    output     [24:0]  a_line,
    output     [255:0] a_data,
    input              a_ack,
    output reg [2:0]   latest = 3'd0,
    output reg [7:0]   par = 8'd0,
    output reg [2:0]   nfields = 3'd0,
    output reg [9:0]   flines = 10'd0,
    output reg [9:0]   prog = 10'd0,
    output reg [2:0]   prog_slot = 3'd0
);
    // the pixel clock's side
    reg [2:0]   slot = 3'd0, e_slot;
    reg [223:0] sh;
    reg [255:0] hold;
    reg [19:0]  hold_a;
    reg         tg = 1'b0, etg = 1'b0, e_f, frz0, frz, dirty = 1'b1;
    reg [9:0]   e_lines;
    always @(posedge llc) begin
        frz0 <= freeze;
        frz <= frz0;
        if (frz)
            dirty <= 1'b1;
        if (we && !frz) begin
            if (w_col[2:0] != 3'd7)
                sh[32 * w_col[2:0] +: 32] <= wd;
            else begin
                hold <= {wd, sh};
                hold_a <= {slot, w_ln, 1'b0, w_col[8:3]};
                tg <= !tg;
            end
        end
        if (eof) begin
            dirty <= frz;
            if (!dirty && !frz) begin
                e_slot <= slot;
                e_f <= eof_f;
                e_lines <= eof_lines;
                etg <= !etg;
                slot <= slot + 3'd1;
            end
        end
    end

    // the memory's side: a few lines wait their turn
    reg         t0, t1, t2, u0, u1, u2;
    reg [275:0] fifo [0:15] /* synthesis syn_ramstyle = "distributed_ram" */;
    reg [4:0]   wp = 5'd0, rp = 5'd0;
    wire [275:0] head = fifo[rp[3:0]];
    // (a_valid a register: what it gates is wide)
    reg         av = 1'b0;
    wire [4:0]  wp_n = t1 != t2 ? wp + 5'd1 : wp, rp_n = a_ack ? rp + 5'd1 : rp;
    assign a_valid = av;
    assign a_line = {head[275:273], 5'd0, head[272:256]};
    assign a_data = head[255:0];
    always @(posedge pclk) begin
        t0 <= tg;
        t1 <= t0;
        t2 <= t1;
        u0 <= etg;
        u1 <= u0;
        u2 <= u1;
        if (t1 != t2)
            fifo[wp[3:0]] <= {hold_a, hold};
        wp <= wp_n;
        rp <= rp_n;
        // (a line's last sixteen pixels taken: the line is in)
        if (a_ack && head[261:256] == 6'd44) begin
            prog <= head[272:263] + 10'd1;
            prog_slot <= head[275:273];
        end
        av <= wp_n != rp_n;
        if (u1 != u2) begin
            latest <= e_slot;
            par[e_slot] <= e_f;
            flines <= e_lines;
            if (nfields != 3'd7)
                nfields <= nfields + 3'd1;
        end
    end
endmodule
