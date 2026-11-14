// sflash_model.v: an SPI NOR flash for the testbenches of rtl/sflash.v: the commands that module
// may send (03 read, 02 page program, 06 write enable, 20 sector erase, 05 status, 9F identity)
// as a flash does them; any other command, and any program or erase below 0x800000, is counted
// (bad_cmd, low_write: there must be none).  The memory kept: 64 kB at 0 and 64 kB at each MB
// from 0x800000 (address bits 23:20 and 15:0).
module sflash_model (
    input      cs_n,
    input      sck,
    input      mosi,
    output reg miso = 1'b0
);
    reg [7:0]  mem [0:16 * 65536 - 1];
    integer    bad_cmd = 0, low_write = 0, n_prog = 0, n_erase = 0, n_read = 0;
    reg        wel = 1'b0, wip = 1'b0;
    reg [7:0]  cmd, sh, ob;
    reg [23:0] a;
    integer    nb, k, np;
    reg [7:0]  page [0:255];
    reg [23:0] pa;
    reg        pending_prog, pending_erase, pending_wel;
    function [19:0] ix(input [23:0] ad);
        ix = {ad[23:20], ad[15:0]};
    endfunction
    initial for (k = 0; k < 16 * 65536; k = k + 1) mem[k] = 8'hFF;
    always @(negedge cs_n) begin
        nb = 0;
        np = 0;
        pending_prog = 0;
        pending_erase = 0;
        pending_wel = 0;
    end
    always @(posedge sck) if (!cs_n) begin
        sh = {sh[6:0], mosi};
        nb = nb + 1;
        if (nb == 8) begin
            cmd = sh;
            if (cmd != 8'h03 && cmd != 8'h02 && cmd != 8'h06 && cmd != 8'h20 && cmd != 8'h05 && cmd != 8'h9F) begin
                bad_cmd = bad_cmd + 1;
                $display("sflash_model: command %h", cmd);
            end
            if (cmd == 8'h06) pending_wel = 1;
        end
        if (nb == 16) a[23:16] = sh;
        if (nb == 24) a[15:8] = sh;
        if (nb == 32) begin
            a[7:0] = sh;
            if (cmd == 8'h02) begin pa = a; pending_prog = 1; end
            if (cmd == 8'h20) pending_erase = 1;
            if (cmd == 8'h03) n_read = n_read + 1;
        end
        if (nb > 32 && nb % 8 == 0 && cmd == 8'h02) begin
            page[np % 256] = sh;
            np = np + 1;
        end
    end
    // what goes out: from the clock's fall on
    always @(negedge sck) if (!cs_n) begin
        if (cmd == 8'h03 && nb >= 32) begin
            if (nb % 8 == 0) begin ob = wip ? 8'hxx : mem[ix(a)]; a = a + 24'd1; end
            miso <= #6 ob[7];
            ob = {ob[6:0], 1'b0};
        end else if (cmd == 8'h05 && nb >= 8) begin
            if (nb % 8 == 0) ob = {6'd0, wel, wip};
            miso <= #6 ob[7];
            ob = {ob[6:0], 1'b0};
        end else if (cmd == 8'h9F && nb >= 8) begin
            if (nb == 8) ob = 8'hEF; else if (nb == 16) ob = 8'h40; else if (nb == 24) ob = 8'h18;
            miso <= #6 ob[7];
            ob = {ob[6:0], 1'b0};
        end
    end
    always @(posedge cs_n) begin
        if (nb == 8 && pending_wel && !wip) wel = 1'b1;
        if (pending_prog && np > 0 && nb % 8 == 0) begin
            if (!pa[23]) begin low_write = low_write + 1; $display("sflash_model: a program at %h", pa); end
            if (wel && !wip) begin
                for (k = 0; k < (np > 256 ? 256 : np); k = k + 1)
                    mem[ix({pa[23:8], pa[7:0] + k[7:0]})] = mem[ix({pa[23:8], pa[7:0] + k[7:0]})] & page[k];
                n_prog = n_prog + 1;
                wel = 1'b0;
                wip = 1'b1;
                wip <= #20000 1'b0;
            end
        end
        if (pending_erase && nb == 32) begin
            if (!a[23]) begin low_write = low_write + 1; $display("sflash_model: an erase at %h", a); end
            if (wel && !wip) begin
                for (k = 0; k < 4096; k = k + 1)
                    mem[ix({a[23:12], k[11:0]})] = 8'hFF;
                n_erase = n_erase + 1;
                wel = 1'b0;
                wip = 1'b1;
                wip <= #100000 1'b0;
            end
        end
    end
endmodule
