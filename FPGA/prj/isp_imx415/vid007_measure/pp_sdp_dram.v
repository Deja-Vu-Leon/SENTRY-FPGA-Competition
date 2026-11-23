// pp_sdp_dram.v - pp_sdp_ram with the memory forced into distributed (LUT) RAM
//
// Same ports and the same behaviour as prj/pre/rtl/pp_sdp_ram.v: simple dual port, registered read with
// enable, read-before-write (reading and writing one address in the same cycle returns the OLD word).
// The array is an asynchronous-read LUT RAM, the read register after it is the same register the
// block-RAM version has inside the ERAM, so the read latency is unchanged (data one clock after re).
//
// The attribute is the one isp_sharpen.v uses for its line stores ((* ram_style = "dram" *) on the reg
// array); the area report of that build lists them under "dram lut" (1040 LUTs for 2 x 1920-deep stores).
// Cost on this device, measured on the v061x area report: about 64 bits per LUT6, i.e.
//   LUTs ~ DW * ceil(2**AW / 64)          (32 deep: 2 bits per LUT; deeper words add F7/F8 muxes, which are free)
// Use it only for memories whose read address comes out of a register or very little logic: the read
// path address -> LUT RAM -> rdata register is a few tenths of a nanosecond longer than address -> ERAM pin.
`timescale 1ns / 1ps

module pp_sdp_dram #(
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

    (* ram_style = "dram" *) reg [DW-1:0] mem [0:(1<<AW)-1];

    always @(posedge clk) begin
        if (re)
            rdata <= mem[raddr];
        if (we)
            mem[waddr] <= wdata;
    end

endmodule
