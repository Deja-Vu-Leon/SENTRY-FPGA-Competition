`timescale 1ns / 1ps
// pad_afifo - asynchronous FIFO, gray-code pointers, first-word-fall-through read, block-RAM memory (2^AW words).
//
//   write side (wclk): wr_en pushes din when !full (a push on a full FIFO is ignored and flagged in `wr_lost`);
//                      `wr_used` = words in the FIFO as seen from the write side (conservative: read pointer is
//                      2-3 clocks old), so free space = 2^AW - wr_used is never over-estimated.
//   read side (rclk):  `dout` is the head word whenever rd_avail != 0; rd_en pops it (ignored when rd_avail == 0).
//                      `rd_avail` = words readable (write pointer 2-3 clocks old: never over-estimated).
// Reset: both domains must be reset together (wrst_n / rrst_n asserted at start-up); no resets after that.
module pad_afifo #(
    parameter DW = 147,
    parameter AW = 9
) (
    input  wire          wclk,
    input  wire          wrst_n,
    input  wire          wr_en,
    input  wire [DW-1:0] din,
    output wire          full,
    output wire [AW:0]   wr_used,
    output reg           wr_lost,
    input  wire          rclk,
    input  wire          rrst_n,
    input  wire          rd_en,
    output wire [DW-1:0] dout,
    output wire [AW:0]   rd_avail
);
    localparam [AW:0] DEPTH = 1 << AW;

    function [AW:0] bin2gray(input [AW:0] b);
        bin2gray = b ^ (b >> 1);
    endfunction
    function [AW:0] gray2bin(input [AW:0] g);
        integer i;
        begin
            gray2bin[AW] = g[AW];
            for (i = AW - 1; i >= 0; i = i - 1) gray2bin[i] = gray2bin[i + 1] ^ g[i];
        end
    endfunction

    reg  [AW:0] rgray;
    // ---------------- write side ----------------
    reg  [AW:0] wptr;
    reg  [AW:0] wgray;
    (* async_reg = "true" *) reg [AW:0] rg_s1, rg_s2;
    reg  [AW:0] rptr_w;                         // read pointer as seen from the write side
    assign wr_used = wptr - rptr_w;
    assign full    = (wr_used == DEPTH);
    wire do_wr = wr_en & ~full;
    always @(posedge wclk or negedge wrst_n)
        if (!wrst_n) begin
            wptr <= 0; wgray <= 0; rg_s1 <= 0; rg_s2 <= 0; rptr_w <= 0; wr_lost <= 1'b0;
        end else begin
            rg_s1 <= rgray; rg_s2 <= rg_s1;
            rptr_w <= gray2bin(rg_s2);
            if (do_wr) begin wptr <= wptr + 1'b1; wgray <= bin2gray(wptr + 1'b1); end
            if (wr_en & full) wr_lost <= 1'b1;
        end

    // ---------------- read side ----------------
    reg  [AW:0] rptr;
    (* async_reg = "true" *) reg [AW:0] wg_s1, wg_s2;
    reg  [AW:0] wptr_r;
    assign rd_avail = wptr_r - rptr;
    wire do_rd = rd_en & (rd_avail != 0);
    wire [AW:0] rptr_n = rptr + do_rd;
    always @(posedge rclk or negedge rrst_n)
        if (!rrst_n) begin
            rptr <= 0; rgray <= 0; wg_s1 <= 0; wg_s2 <= 0; wptr_r <= 0;
        end else begin
            wg_s1 <= wgray; wg_s2 <= wg_s1;
            wptr_r <= gray2bin(wg_s2);
            rptr <= rptr_n; rgray <= bin2gray(rptr_n);
        end

    // memory: head word is re-read every clock from the (new) read pointer -> first-word-fall-through
    reg [DW-1:0] mem [0:(1 << AW)-1];
    reg [DW-1:0] dout_q;
    always @(posedge wclk) if (do_wr) mem[wptr[AW-1:0]] <= din;
    always @(posedge rclk) dout_q <= mem[rptr_n[AW-1:0]];
    assign dout = dout_q;
endmodule
