// tmds.v: a TMDS channel's encoder [DVI 1.0 3.2, HDMI 1.4 5.4.4], N characters a clock (N pixels of
// the line side by side, the first at the low end): a byte while its de, else the ten bits of tok
// as they are (a control character: hdmi_scr.v makes them).  N + 4 clocks from input to q; of each
// character q[0] goes first.
//
// The DC balance's running count threads through every character, N of them a clock.  It takes
// nine values (-8 to 8 in twos: every byte from every count tried, sim/tmds_tb.py), so each
// character is made a table: the count after it for each count before it; the tables of a clock's
// characters are put together ahead of time, one a stage (the count after k characters for each
// count before the first), and the loop itself is one look-up, whatever N.

module tmds_enc #(parameter N = 1) (
    input                     clk,
    input      [8 * N - 1:0]  d,
    input      [10 * N - 1:0] tok,
    input      [N - 1:0]      de,
    output reg [10 * N - 1:0] q
);
    localparam T = 36;                          // a table: nine counts, four bits each (count / 2 + 4)

    function [3:0] ones(input [7:0] v);
        ones = v[0] + v[1] + v[2] + v[3] + v[4] + v[5] + v[6] + v[7];
    endfunction
    function [8:0] minimise(input [7:0] v);     // the transition-minimised word
        reg     x;
        integer i;
        begin
            x = ones(v) > 4'd4 || (ones(v) == 4'd4 && !v[0]);
            minimise[0] = v[0];
            for (i = 1; i < 8; i = i + 1)
                minimise[i] = x ? ~(minimise[i - 1] ^ v[i]) : minimise[i - 1] ^ v[i];
            minimise[8] = ~x;
        end
    endfunction
    function [3:0] look(input [T - 1:0] tab, input [3:0] s);
        look = tab[4 * s +: 4];
    endfunction
    function [T - 1:0] after(input [T - 1:0] next, input [T - 1:0] first);      // first, then next
        integer s;
        begin
            for (s = 0; s < 9; s = s + 1)
                after[4 * s +: 4] = look(next, first[4 * s +: 4]);
        end
    endfunction

    integer k, j, s;

    // stage 1: each character's minimised word and its ones less its zeros
    reg [9 * N - 1:0] m_q;
    reg [5 * N - 1:0] diff_q;
    reg [10 * N - 1:0] tok_q;
    reg [N - 1:0]     de_q = {N{1'b0}};
    reg [8:0]         m;
    always @(posedge clk) begin
        for (k = 0; k < N; k = k + 1) begin
            m = minimise(d[8 * k +: 8]);
            m_q[9 * k +: 9] <= m;
            diff_q[5 * k +: 5] <= {ones(m[7:0]), 1'b0} - 5'd8;
        end
        tok_q <= tok;
        de_q <= de;
    end

    // stage 2: for the count zero (z), above (p) and below (n): the character sent and what it
    // adds.  As it is with bit 9 saying which way round (count or word balanced); inverted; plain
    reg [10 * N - 1:0] qz, qp, qn;
    reg [5 * N - 1:0]  dz, dp, dn;
    reg [N - 1:0]      de_r = {N{1'b0}};
    reg signed [4:0]   diff, d_bal, d_inv, d_pla;
    reg [8:0]          w;
    reg [9:0]          q_bal, q_inv, q_pla;
    always @(posedge clk) begin
        for (k = 0; k < N; k = k + 1) begin
            w = m_q[9 * k +: 9];
            diff = diff_q[5 * k +: 5];
            q_bal = {~w[8], w[8], w[8] ? w[7:0] : ~w[7:0]};
            d_bal = w[8] ? diff : -diff;
            q_inv = {1'b1, w[8], ~w[7:0]};
            d_inv = $signed({3'b0, w[8], 1'b0}) - diff;
            q_pla = {1'b0, w[8], w[7:0]};
            d_pla = diff - $signed({3'b0, ~w[8], 1'b0});
            if (!de_q[k]) begin
                qz[10 * k +: 10] <= tok_q[10 * k +: 10];
                qp[10 * k +: 10] <= tok_q[10 * k +: 10];
                qn[10 * k +: 10] <= tok_q[10 * k +: 10];
            end else begin
                qz[10 * k +: 10] <= q_bal;
                qp[10 * k +: 10] <= diff == 5'sd0 ? q_bal : diff > 5'sd0 ? q_inv : q_pla;
                qn[10 * k +: 10] <= diff == 5'sd0 ? q_bal : diff < 5'sd0 ? q_inv : q_pla;
            end
            dz[5 * k +: 5] <= d_bal;
            dp[5 * k +: 5] <= diff == 5'sd0 ? d_bal : diff > 5'sd0 ? d_inv : d_pla;
            dn[5 * k +: 5] <= diff == 5'sd0 ? d_bal : diff < 5'sd0 ? d_inv : d_pla;
        end
        de_r <= de_q;
    end

    // stages 3 to N + 2: each character's table (f_d[0]); then, a stage a character, the tables
    // put together: pre[j]'s slot i (i <= j) is the count after characters 0 to i
    reg [T * N - 1:0] f_d [0:N - 1];
    reg [T * N - 1:0] pre [0:N - 1];
    reg [T - 1:0]     tab;
    initial                                     // (as the FPGA starts: the count's loop must not
        for (j = 0; j < N; j = j + 1) begin     // begin on unknowns in simulation; the first
            f_d[j] = {T * N{1'b0}};             // blanking sets the count)
            pre[j] = {T * N{1'b0}};
        end
    always @(posedge clk) begin
        for (k = 0; k < N; k = k + 1) begin
            for (s = 0; s < 9; s = s + 1)
                tab[4 * s +: 4] = !de_r[k] ? 4'd4 :
                                  s == 4 ? 4'd4 + dz[5 * k + 1 +: 4] :
                                  s > 4 ? s[3:0] + dp[5 * k + 1 +: 4] : s[3:0] + dn[5 * k + 1 +: 4];
            f_d[0][T * k +: T] <= tab;
            if (k == 0)
                pre[0][0 +: T] <= tab;
        end
        for (j = 1; j < N; j = j + 1) begin
            f_d[j] <= f_d[j - 1];
            for (k = 0; k < j; k = k + 1)
                pre[j][T * k +: T] <= pre[j - 1][T * k +: T];
            pre[j][T * j +: T] <= after(f_d[j - 1][T * j +: T], pre[j - 1][T * (j - 1) +: T]);
        end
    end

    // the characters to choose from, kept until their counts are known (N + 1 stages)
    reg [30 * N - 1:0] q_d [0:N];
    always @(posedge clk) begin
        q_d[0] <= {qn, qp, qz};
        for (j = 1; j <= N; j = j + 1)
            q_d[j] <= q_d[j - 1];
    end

    // stage N + 3: the loop: the count (as count / 2 + 4) before each of the clock's characters
    reg [3:0]         cnt = 4'd4;
    reg [4 * N - 1:0] t;
    always @(posedge clk) begin
        cnt <= look(pre[N - 1][T * (N - 1) +: T], cnt);
        t[3:0] <= cnt;
        for (k = 1; k < N; k = k + 1)
            t[4 * k +: 4] <= look(pre[N - 1][T * (k - 1) +: T], cnt);
    end

    // stage N + 4: each character by its count
    always @(posedge clk)
        for (k = 0; k < N; k = k + 1)
            q[10 * k +: 10] <= t[4 * k +: 4] == 4'd4 ? q_d[N][10 * k +: 10] :
                               t[4 * k +: 4] > 4'd4 ? q_d[N][10 * (N + k) +: 10] : q_d[N][10 * (2 * N + k) +: 10];
endmodule
