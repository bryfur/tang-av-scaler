// audio_fifo.v: the sound through the CPU (sw/audio.c: the surround decoder).  Each pair of samples
// from the converter waits here for the CPU; what the CPU makes of a pair, six channels, waits for
// its sample time to go out (hdmi_audio.v mc).  On the system clock, in the register bus:
//
//   AUD   W  0 on: the CPU's six channels go out (else the converter's pair as it comes, and
//            nothing is kept here), 1 both FIFOs emptied (a pulse)
//         R  9:0 pairs waiting for the CPU, 25:16 sets waiting to go out, 31:26 sample times with
//            nothing to send (silence went out; counts to 63)
//   AUDL  R  the oldest pair's left sample (23:0; 31 one waits)
//   AUDR  R  ... its right one
//   AUDO  W  a set's channels in turn: left, right, centre, LFE, left surround, right surround
//            (23:0); the sixth puts the set in and takes the oldest pair out: a set a pair
//
// The sets go out a sample time each once OUT_START wait (4 ms: the CPU has other work between
// its turns here); with none left, silence, and they wait for OUT_START again.

module audio_fifo #(
    parameter OUT_START = 192
) (
    input              clk,
    input              we,
    input      [7:0]   addr,
    input      [31:0]  wdata,
    input              in_tick,         // changes with each new pair (another clock's; the pair stays)
    input      [23:0]  in_l,
    input      [23:0]  in_r,
    output     [31:0]  r_stat,
    output     [31:0]  r_l,
    output     [31:0]  r_r,
    output reg         on = 1'b0,
    output reg         o_tick = 1'b0,   // changes with each new set
    output reg [143:0] o_s = 144'd0     // {rs, ls, lfe, c, r, l}
);
    localparam A_AUD = 8'h54, A_AUDO = 8'h57;

    // the sample time, here
    reg        t0 = 1'b0, t1 = 1'b0, t2 = 1'b0;
    wire       tick = t1 != t2;
    wire       clr = we && addr == A_AUD && wdata[1];
    always @(posedge clk) begin
        t0 <= in_tick;
        t1 <= t0;
        t2 <= t1;
        if (we && addr == A_AUD)
            on <= wdata[0];
    end

    // ---- the pairs waiting: 512 of them; the oldest in a register ----
    reg [47:0] im [0:511];
    reg [8:0]  i_wp = 9'd0, i_rp = 9'd0;
    reg [9:0]  i_n = 10'd0;
    reg [47:0] i_q, i_head;
    reg        i_have = 1'b0;           // i_head is the oldest pair
    reg [1:0]  i_ld = 2'd0;             // (the memory's word on its way to i_head)
    reg [2:0]  o_k = 3'd0;              // the set's channel next written
    wire       set_in = we && addr == A_AUDO && o_k == 3'd5;
    wire       i_push = tick && on && i_n != 10'd512;
    wire       i_pop = set_in && i_have;
    assign r_l = {i_have, 7'd0, i_head[23:0]};
    assign r_r = {i_have, 7'd0, i_head[47:24]};
    always @(posedge clk) begin
        if (i_push) begin
            im[i_wp] <= {in_r, in_l};
            i_wp <= i_wp + 9'd1;
        end
        i_q <= im[i_rp];
        i_n <= i_n + (i_push ? 10'd1 : 10'd0) - (i_pop ? 10'd1 : 10'd0);
        // the oldest pair into its register: when there is one and the register is empty
        i_ld <= {i_ld[0], 1'b0};
        if (i_pop) begin
            i_have <= 1'b0;
            i_rp <= i_rp + 9'd1;
        end else if (!i_have && i_ld == 2'd0 && i_n != 10'd0)
            i_ld <= 2'b01;              // (a clock for the address, one for the memory)
        if (i_ld[1]) begin
            i_head <= i_q;
            i_have <= 1'b1;
        end
        if (clr || !on) begin
            i_wp <= 9'd0;
            i_rp <= 9'd0;
            i_n <= 10'd0;
            i_have <= 1'b0;
            i_ld <= 2'd0;
        end
    end

    // ---- the sets waiting: 512 of them ----
    reg [143:0] om [0:511];
    reg [8:0]   o_wp = 9'd0, o_rp = 9'd0;
    reg [9:0]   o_n = 10'd0;
    reg [119:0] o_part;                 // the set's first five channels
    reg [143:0] o_q;
    reg         going = 1'b0;
    reg [9:0]   o_n1 = 10'd0, o_n2 = 10'd0;     // (the count two clocks ago: what was in then is in o_q now)
    reg [5:0]   dry = 6'd0;
    wire        o_push = set_in && o_n != 10'd512;
    wire        o_pop = tick && on && going && o_n2 != 10'd0;
    assign r_stat = {dry, o_n, 6'd0, i_n};
    always @(posedge clk) begin
        if (we && addr == A_AUDO) begin
            o_k <= o_k == 3'd5 ? 3'd0 : o_k + 3'd1;
            if (o_k != 3'd5)
                o_part[24 * o_k +: 24] <= wdata[23:0];
        end
        if (o_push) begin
            om[o_wp] <= {wdata[23:0], o_part};
            o_wp <= o_wp + 9'd1;
        end
        o_q <= om[o_rp];
        o_n <= o_n + (o_push ? 10'd1 : 10'd0) - (o_pop ? 10'd1 : 10'd0);
        o_n1 <= o_pop ? 10'd0 : o_n;
        o_n2 <= o_pop ? 10'd0 : o_n1;
        if (o_n >= OUT_START)
            going <= 1'b1;
        // a sample time: the oldest set, or silence
        if (o_pop) begin
            o_s <= o_q;
            o_tick <= !o_tick;
            o_rp <= o_rp + 9'd1;
        end else if (tick && on) begin
            o_s <= 144'd0;
            o_tick <= !o_tick;
            if (going) begin
                going <= 1'b0;
                if (dry != 6'd63)
                    dry <= dry + 6'd1;
            end
        end
        if (clr || !on) begin
            o_wp <= 9'd0;
            o_rp <= 9'd0;
            o_n <= 10'd0;
            o_k <= 3'd0;
            going <= 1'b0;
            o_n1 <= 10'd0;
            o_n2 <= 10'd0;
            if (clr)
                dry <= 6'd0;
        end
    end
endmodule
