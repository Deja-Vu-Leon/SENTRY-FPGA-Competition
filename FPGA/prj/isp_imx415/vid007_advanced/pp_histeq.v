// pp_histeq.v - streaming histogram equalisation, 4-pixel-parallel 8-bit gray stream
//
// Bus (gray branch): I_tdata[8*i+7 : 8*i] = pixel i of the beat, i = 0..3.
//
// Frame schedule (decided at each frame start, I_tvalid & I_tuser):
//   ACC  frame: histogram of pixel 0 of every beat (1/4 subsampling), N = #beats
//   CALC frame: in the background, recip = floor(255 * 2^24 / N) by a serial divider,
//               then for k = 0..255: cdf += hist[k], hist[k] = 0,
//               lut_next[k] = min(255, (cdf * recip + 2^23) >> 24)
//   next frame start: lut <= lut_next (whole table at once, never mid-frame), back to ACC
// So the LUT is refreshed every 2 frames and frame n uses the histogram of frame n-2
// (identity LUT until the first update). The computation takes ~300 cycles; if it is
// still running at a frame start (tiny frames), the swap simply waits one more frame.
// I_en = 0 passes pixels through (statistics keep running).
//
// Latency 2 cycles. Never stalls; I_tready mirrors O_tready.
`timescale 1ns / 1ps

module pp_histeq #(
    parameter CW = 22                   // bin / pixel counter width: 4K/4 = 2.07M < 2^22
) (
    input               I_clk,
    input               I_rst_n,
    input               I_en,

    input       [31:0]  I_tdata,
    input               I_tvalid,
    input               I_tlast,
    input               I_tuser,
    output              I_tready,

    output reg  [31:0]  O_tdata,
    output reg          O_tvalid,
    output reg          O_tlast,
    output reg          O_tuser,
    input               O_tready,

    output reg  [15:0]  O_lut_updates   // debug: number of LUT swaps
);

    assign I_tready = O_tready;

    localparam S_IDLE = 2'd0, S_ACC = 2'd1, S_CALC = 2'd2;
    localparam C_IDLE = 2'd0, C_DIV = 2'd1, C_BIN = 2'd2, C_DONE = 2'd3;

    reg [1:0]    state;
    reg [1:0]    cst;
    reg [CW-1:0] npix;
    reg          act;                   // active LUT bank; the other one is "lut_next"

    // Synchronous init: clears the histogram and loads an identity LUT over 256 cycles.
    // Async-resetting the 256x22 histogram plus the two 256x8 LUTs (about 10k flops)
    // builds a huge reset fanout; in the integrated design that showed up as the worst
    // recovery/removal violation, so these arrays are written synchronously instead.
    reg [8:0] init_cnt;
    reg       init_done;

    always @(posedge I_clk or negedge I_rst_n) begin
        if (!I_rst_n) begin
            init_cnt  <= 9'd0;
            init_done <= 1'b0;
        end else if (!init_done) begin
            init_cnt <= init_cnt + 1'b1;
            if (init_cnt == 9'd255)
                init_done <= 1'b1;
        end
    end

    wire sof     = I_tvalid & I_tuser & init_done;
    wire swap    = sof && state == S_CALC && cst == C_DONE;
    wire start   = sof && state == S_ACC;
    wire acc_now = I_tvalid && ((state == S_ACC && !I_tuser) || swap || (sof && state == S_IDLE));

    // ------------------------------------------------------------ frame FSM, LUT swap
    // Timing fork: hist / lut / lut_next are block RAM. The swap now flips the bank
    // pointer `act` instead of copying 256 entries; lut_next is the other half of the
    // same RAM. The identity LUT is written into bank 0 (act resets to 0) during init.
    always @(posedge I_clk or negedge I_rst_n) begin
        if (!I_rst_n) begin
            state         <= S_IDLE;
            npix          <= {CW{1'b0}};
            O_lut_updates <= 16'd0;
            act           <= 1'b0;
        end else if (init_done) begin
            if (sof) begin
                case (state)
                    S_IDLE: state <= S_ACC;
                    S_ACC:  state <= S_CALC;
                    S_CALC: if (cst == C_DONE) state <= S_ACC;
                    default: state <= S_IDLE;
                endcase
            end
            if (swap) begin
                act           <= ~act;
                O_lut_updates <= O_lut_updates + 1'b1;
            end
            if (acc_now)
                npix <= (sof ? {CW{1'b0}} : npix) + 1'b1;
        end
    end

    // ------------------------------------------------------------ background LUT computation
    reg [5:0]     div_cnt;
    reg [31:0]    num, quo;
    reg [CW-1:0]  rem, den;
    reg [8:0]     kbin;                 // 0..256
    reg [CW-1:0]  cdf;
    reg [CW-1:0]  prod_in;
    reg [7:0]     ka, kb;
    reg           va, vb;
    reg [CW+31:0] prod;

    wire [CW:0]    rem_sh = {rem, num[31]};
    wire [CW-1:0]  hk;                  // hist[kbin], from the RAM read prefetched one cycle earlier
    wire [CW+31:0] rnd    = prod + (1 << 23);

    always @(posedge I_clk or negedge I_rst_n) begin
        if (!I_rst_n) begin
            cst <= C_IDLE; div_cnt <= 6'd0; num <= 32'd0; quo <= 32'd0; rem <= {CW{1'b0}};
            den <= {CW{1'b0}}; kbin <= 9'd0; cdf <= {CW{1'b0}}; prod_in <= {CW{1'b0}};
            ka <= 8'd0; kb <= 8'd0; va <= 1'b0; vb <= 1'b0; prod <= {(CW+32){1'b0}};
        end else begin
            case (cst)
                C_IDLE: if (start) begin
                    num     <= 32'd255 << 24;
                    quo     <= 32'd0;
                    rem     <= {CW{1'b0}};
                    den     <= npix;
                    div_cnt <= 6'd32;
                    cst     <= C_DIV;
                end
                C_DIV: begin
                    if (rem_sh >= {1'b0, den}) begin
                        rem <= rem_sh - {1'b0, den};
                        quo <= {quo[30:0], 1'b1};
                    end else begin
                        rem <= rem_sh[CW-1:0];
                        quo <= {quo[30:0], 1'b0};
                    end
                    num     <= num << 1;
                    div_cnt <= div_cnt - 1'b1;
                    if (div_cnt == 6'd1) begin
                        kbin <= 9'd0;
                        cdf  <= {CW{1'b0}};
                        cst  <= C_BIN;
                    end
                end
                C_BIN: begin
                    if (kbin != 9'd256) begin
                        cdf     <= cdf + hk;
                        prod_in <= cdf + hk;
                        ka      <= kbin[7:0];
                        va      <= 1'b1;
                        kbin    <= kbin + 1'b1;
                    end else begin
                        va <= 1'b0;
                        if (!va && !vb)
                            cst <= C_DONE;
                    end
                end
                C_DONE: if (swap) cst <= C_IDLE;
            endcase

            // multiply + write stages (quo stays stable during C_BIN)
            vb   <= va;
            kb   <= ka;
            prod <= prod_in * quo;
        end
    end

    // ------------------------------------------------------------ histogram bins
    // One 256 x CW block RAM, registered read (read-before-write). Accumulate is a two-
    // cycle read-modify-write: the beat's pixel-0 value is the read address at the edge
    // that accepts it (p_v/p_addr remember it), the +1 and the write happen in the next
    // cycle; back-to-back equal addresses are served by forwarding the value just written.
    // The background calculation prefetches hist[kbin+1] so hk is hist[kbin] in the same
    // cycle as before: its timing, and with it the moment cst reaches C_DONE, is unchanged.
    // Accumulate and calculation never overlap (the original gave the clear priority too).
    wire              calc_rd = (cst == C_DIV) || (cst == C_BIN);
    wire [7:0]        h_ra    = calc_rd ? ((cst == C_DIV) ? 8'd0 : (kbin[7:0] + 8'd1)) : I_tdata[7:0];
    wire [CW-1:0]     h_rd;
    reg               p_v;
    reg  [7:0]        p_addr;
    reg               lw_v;
    reg  [7:0]        lw_addr;
    reg  [CW-1:0]     lw_data;
    wire [CW-1:0]     h_base  = (lw_v && lw_addr == p_addr) ? lw_data : h_rd;
    wire [CW-1:0]     h_inc   = h_base + 1'b1;
    wire              clr_c   = (cst == C_BIN) && (kbin != 9'd256);

    wire              h_we    = !init_done || clr_c || p_v;
    wire [7:0]        h_wa    = !init_done ? init_cnt[7:0] : clr_c ? kbin[7:0] : p_addr;
    wire [CW-1:0]     h_wd    = (!init_done || clr_c) ? {CW{1'b0}} : h_inc;

    assign hk = h_rd;

    pp_sdp_ram #(.DW(CW), .AW(8)) u_hist (
        .clk(I_clk), .we(h_we), .waddr(h_wa), .wdata(h_wd),
        .re(1'b1), .raddr(h_ra), .rdata(h_rd)
    );

    always @(posedge I_clk or negedge I_rst_n) begin
        if (!I_rst_n) begin
            p_v <= 1'b0; p_addr <= 8'd0; lw_v <= 1'b0; lw_addr <= 8'd0; lw_data <= {CW{1'b0}};
        end else begin
            p_v    <= acc_now && init_done && !clr_c;
            p_addr <= I_tdata[7:0];
            lw_v   <= p_v && init_done && !clr_c;
            lw_addr <= p_addr;
            lw_data <= h_inc;
        end
    end

    // ------------------------------------------------------------ apply LUT
    // Four identical copies of a 2 x 256 x 8 RAM (bank = act), one read port each. The read
    // address is the incoming pixel at the edge that registers d1, with the bank pointer as it
    // is AFTER a swap at that same edge; the lookup the original did in the next cycle on the
    // lut array therefore sees the same table. The only other write to the active bank is
    // the identity init, so a lookup that coincides with the write of its own entry takes
    // the (identity) pixel itself instead of the stale RAM word.
    wire       act_rd = act ^ swap;
    wire       lw_we  = !init_done || vb;
    wire [8:0] lw_a   = !init_done ? {act, init_cnt[7:0]} : {~act, kb};
    wire [7:0] lw_d   = !init_done ? init_cnt[7:0] : ((|rnd[CW+31:32]) ? 8'd255 : rnd[31:24]);
    wire [31:0] lut_q;
    reg  [3:0]  byp;

    genvar gi;
    generate
        for (gi = 0; gi < 4; gi = gi + 1) begin : g_lut
            pp_sdp_ram #(.DW(8), .AW(9)) u_lut (
                .clk(I_clk), .we(lw_we), .waddr(lw_a), .wdata(lw_d),
                .re(I_tvalid), .raddr({act_rd, I_tdata[8*gi +: 8]}), .rdata(lut_q[8*gi +: 8])
            );
        end
    endgenerate

    reg [31:0] d1;
    reg        v1, last1, user1, en1;
    integer i;
    always @(posedge I_clk or negedge I_rst_n) begin
        if (!I_rst_n) begin
            d1 <= 32'd0; v1 <= 1'b0; last1 <= 1'b0; user1 <= 1'b0; en1 <= 1'b0;
            O_tdata <= 32'd0; O_tvalid <= 1'b0; O_tlast <= 1'b0; O_tuser <= 1'b0;
            byp <= 4'd0;
        end else begin
            v1 <= I_tvalid;
            if (I_tvalid) begin
                d1    <= I_tdata;
                last1 <= I_tlast;
                user1 <= I_tuser;
                en1   <= I_en;
                for (i = 0; i < 4; i = i + 1)
                    byp[i] <= !init_done && (I_tdata[8*i +: 8] == init_cnt[7:0]);
            end
            O_tvalid <= v1;
            if (v1) begin
                for (i = 0; i < 4; i = i + 1)
                    O_tdata[8*i +: 8] <= (en1 & init_done) ? (byp[i] ? d1[8*i +: 8] : lut_q[8*i +: 8])
                                                           : d1[8*i +: 8];
                O_tlast <= last1;
                O_tuser <= user1;
            end else begin
                O_tlast <= 1'b0;
                O_tuser <= 1'b0;
            end
        end
    end

endmodule
