// pp_sdp_ram.v - simple dual-port RAM, registered read, read-before-write
//
// Written so TD infers an ERAM (same behaviour as the vendor wrapper
// ui_ram_demosaic: SDP, NOREG, port B READBEFOREWRITE). Reading and writing the
// same address in one cycle returns the OLD word, which is exactly what a
// line-delay buffer needs (raddr == waddr).
`timescale 1ns / 1ps

module pp_sdp_ram #(
    parameter DW = 32,
    parameter AW = 10
) (
    input                   clk,
    input                   we,
    input      [AW-1:0]     waddr,
    input      [DW-1:0]     wdata,
    input                   re,
    input      [AW-1:0]     raddr,
    output reg [DW-1:0]     rdata
);

    reg [DW-1:0] mem [0:(1<<AW)-1];

    always @(posedge clk) begin
        if (re)
            rdata <= mem[raddr];
        if (we)
            mem[waddr] <= wdata;
    end

endmodule
