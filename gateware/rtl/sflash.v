// sflash.v: the SOM's configuration flash (16 MB of SPI NOR: the bitstream in its first 5 MB) as the
// board's own storage: its upper half, 0x800000 on, for what must outlast the power (the settings,
// the scaler's tables, the network's weights: sw/store.c).  The FPGA's configuration pins are plain
// pins once it is configured (gowin/avb.tcl: use_mspi_as_gpio).
//
// Not a plain SPI port: the commands are made here, a fixed few, and the CPU's program (or the host,
// through the monitor) gives only an address and data.  What can change the flash (program, erase)
// is done only at 0x800000 or above and with a key in the command: nothing written to these
// registers, by a fault or by design, can touch the bitstream, the status register or the whole
// chip.  A page program cannot leave its 256-byte page and a sector erase its 4096 bytes (the
// flash's own rules), so the address checked is the whole of it.
//
// Registers (A = 8'h68):
//   A   W  FLC   31:28 what, 23:0 an address:
//                  1 READ   a read begun at the address (03); its first four bytes then in FLD
//                  2 NEXT   in a read: the next four bytes into FLD; in a program: FLD's four sent
//                  3 END    the read or the program ended (the chip's select let go: a program
//                           starts then, a few ms: FLS's status says when it is over)
//                  4 PROG   a page program begun at the address (06, then 02): 27:24 must be A and
//                           the address 0x800000 or more, else nothing is done (FLS 1)
//                  5 ERASE  the address's 4096 bytes erased (06, then 20): as PROG; some 50 ms and more
//                  6 STATUS the flash's status byte into FLD (05): bit 0 it is busy writing
//                  7 ID     its three identity bytes into FLD (9F): 23:16 the maker's
//                a read or a program still open when another is begun is ended first
//   A+1 RW FLD   four bytes, the first in 7:0
//   A+2 R  FLS   0 busy (a command here is not taken), 1 the last PROG or ERASE was refused,
//                2 a read or program is open, 3 it is a program
//
// The clock is the system's / 4 (12.5 MHz), mode 0: the data out changes while the clock is low,
// the flash's is taken as the clock rises (a register at the pin first).

module sflash #(
    parameter [7:0] A = 8'h68
) (
    input             clk,
    input             we,
    input      [7:0]  addr,
    input      [31:0] wdata,
    output     [31:0] q_d,
    output     [31:0] q_s,
    output reg        f_cs_n = 1'b1,
    output reg        f_sck = 1'b0,
    output reg        f_mosi = 1'b0,
    input             f_miso,
    output            f_wp_n,
    output            f_hold_n
);
    assign f_wp_n = 1'b1;
    assign f_hold_n = 1'b1;

    localparam O_READ = 4'd1, O_NEXT = 4'd2, O_END = 4'd3, O_PROG = 4'd4, O_ERASE = 4'd5, O_STATUS = 4'd6, O_ID = 4'd7;
    // a step of a command
    localparam T_DONE = 3'd0, T_CSL = 3'd1, T_CSH = 3'd2, T_TX = 3'd3, T_RX = 3'd4;

    reg [31:0] fld = 32'd0;
    reg        busy = 1'b0, refused = 1'b0, open = 1'b0, prog = 1'b0;
    reg [3:0]  op;
    reg [23:0] ad;
    reg [2:0]  step;
    reg        run = 1'b0;              // (a step's bits or wait are on their way)
    reg [5:0]  n;
    reg [1:0]  ph;
    reg [31:0] tx, rx;
    reg        rxing, mi;
    assign q_d = fld;
    assign q_s = {28'd0, prog, open, refused, busy};

    // the command's steps: what, how many bits, the bits sent (from the top)
    reg [2:0]  t;
    reg [5:0]  tn;
    reg [31:0] td;
    wire [31:0] fsw = {fld[7:0], fld[15:8], fld[23:16], fld[31:24]};
    always @(*) begin
        t = T_DONE;
        tn = 6'd0;
        td = 32'd0;
        case (op)
            O_READ: case (step)
                3'd0: t = T_CSL;
                3'd1: begin t = T_TX; tn = 6'd32; td = {8'h03, ad}; end
                3'd2: begin t = T_RX; tn = 6'd32; end
                default: ;
            endcase
            O_NEXT: case (step)
                3'd0: if (prog) begin t = T_TX; tn = 6'd32; td = fsw; end else begin t = T_RX; tn = 6'd32; end
                default: ;
            endcase
            O_END: case (step)
                3'd0: t = T_CSH;
                default: ;
            endcase
            O_PROG, O_ERASE: case (step)
                3'd0: t = T_CSL;
                3'd1: begin t = T_TX; tn = 6'd8; td = {8'h06, 24'd0}; end
                3'd2: t = T_CSH;
                3'd3: t = T_CSL;
                3'd4: begin t = T_TX; tn = 6'd32; td = {op == O_PROG ? 8'h02 : 8'h20, ad}; end
                3'd5: if (op == O_ERASE) t = T_CSH;
                default: ;
            endcase
            O_STATUS, O_ID: case (step)
                3'd0: t = T_CSL;
                3'd1: begin t = T_TX; tn = 6'd8; td = {op == O_STATUS ? 8'h05 : 8'h9F, 24'd0}; end
                3'd2: begin t = T_RX; tn = op == O_STATUS ? 6'd8 : 6'd24; end
                3'd3: t = T_CSH;
                default: ;
            endcase
            default: ;
        endcase
    end

    wire [3:0] w_op = wdata[31:28];
    wire       w_ok = (w_op != O_PROG && w_op != O_ERASE) || (wdata[23] && wdata[27:24] == 4'hA);
    reg        pre = 1'b0;              // (what was open is ended before the command's own steps)
    always @(posedge clk) begin
        mi <= f_miso;
        if (we && addr == A + 8'd1 && !busy)
            fld <= wdata;
        if (we && addr == A && !busy && w_op >= O_READ && w_op <= O_ID) begin
            if (!w_ok)
                refused <= 1'b1;
            else if (w_op == O_NEXT && !open)
                ;                       // (nothing open: nothing to do)
            else begin
                if (w_op == O_PROG || w_op == O_ERASE)
                    refused <= 1'b0;
                busy <= 1'b1;
                op <= w_op;
                ad <= wdata[23:0];
                step <= 3'd0;
                run <= 1'b0;
                pre <= open && w_op != O_NEXT && w_op != O_END;
            end
        end
        if (busy && !run) begin
            if (pre) begin              // the select let go, and a wait
                f_cs_n <= 1'b1;
                f_sck <= 1'b0;
                open <= 1'b0;
                prog <= 1'b0;
                pre <= 1'b0;
                run <= 1'b1;
                rxing <= 1'b0;
                n <= 6'd0;
                ph <= 2'd0;
                tx <= 32'd0;
                step <= 3'd7;           // (the wait's end counts it on to 0)
            end else case (t)
                T_DONE: begin
                    busy <= 1'b0;
                    if (op == O_READ)
                        {open, prog} <= 2'b10;
                    if (op == O_PROG)
                        {open, prog} <= 2'b11;
                    // what was read, the first byte lowest
                    if (op == O_READ || (op == O_NEXT && !prog))
                        fld <= {rx[7:0], rx[15:8], rx[23:16], rx[31:24]};
                    if (op == O_STATUS)
                        fld <= {24'd0, rx[7:0]};
                    if (op == O_ID)
                        fld <= {8'd0, rx[23:0]};
                end
                T_CSL: begin
                    f_cs_n <= 1'b0;
                    f_sck <= 1'b0;
                    step <= step + 3'd1;
                end
                T_CSH: begin            // (and a wait before the select can go down again)
                    f_cs_n <= 1'b1;
                    f_sck <= 1'b0;
                    open <= 1'b0;
                    prog <= 1'b0;
                    run <= 1'b1;
                    rxing <= 1'b0;
                    n <= 6'd0;
                    ph <= 2'd0;
                    tx <= 32'd0;
                end
                T_TX, T_RX: begin
                    run <= 1'b1;
                    rxing <= t == T_RX;
                    n <= tn;
                    ph <= 2'd0;
                    tx <= td;
                    f_mosi <= t == T_TX ? td[31] : 1'b0;
                end
                default: busy <= 1'b0;
            endcase
        end
        if (run) begin
            ph <= ph + 2'd1;
            if (n == 6'd0) begin        // a wait: sixteen clocks with the select up
                if (ph == 2'd3) begin
                    tx <= tx + 32'd1;
                    if (tx[1:0] == 2'd3) begin
                        run <= 1'b0;
                        step <= step + 3'd1;
                    end
                end
            end else case (ph)
                2'd1: f_sck <= 1'b1;    // the clock rises: the flash takes our bit
                2'd2: if (rxing)        // its own bit: as it was at the pin when the clock rose (out since the fall)
                    rx <= {rx[30:0], mi};
                2'd3: begin             // the clock falls: the next bit out
                    f_sck <= 1'b0;
                    tx <= {tx[30:0], 1'b0};
                    f_mosi <= rxing ? 1'b0 : tx[30];
                    n <= n - 6'd1;
                    if (n == 6'd1) begin
                        run <= 1'b0;
                        step <= step + 3'd1;
                    end
                end
                default: ;
            endcase
        end
    end
endmodule
