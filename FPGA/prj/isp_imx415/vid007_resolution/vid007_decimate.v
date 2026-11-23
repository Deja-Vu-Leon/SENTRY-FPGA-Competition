`timescale 1ns/1ps

// Select complete Bayer 2x2 cells. Each reduced line group keeps the two
// consecutive source rows required by GBRG and emits four pixels per beat.
module vid007_decimate (
    input wire clk, reset_n, valid, sof,
    input wire [31:0] pixels,
    input wire [1:0] resolution,
    output wire out_valid, out_sof,
    output wire [31:0] out_pixels
);
    reg [8:0] column;
    reg [2:0] row_phase;
    reg [15:0] first_pair;
    wire [8:0] x = sof ? 9'd0 : column;
    wire [2:0] y = sof ? 3'd0 : row_phase;
    wire quarter = resolution == 2;
    wire keep_row = quarter ? y[2:1] == 0 : !y[1];
    wire keep_pair = quarter ? !x[0] : 1'b1;
    wire output_pair = quarter ? x[1:0] == 2 : x[0];
    wire reduced = resolution == 1 || quarter;
    assign out_valid = valid && (!reduced || (keep_row && output_pair));
    assign out_sof = reduced ? x == (quarter ? 9'd2 : 9'd1) && y == 0 && first_row : sof;
    assign out_pixels = reduced ? {pixels[15:0],first_pair} : pixels;

    reg first_row;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            column <= 0;
            row_phase <= 0;
            first_row <= 0;
        end else if(valid) begin
            column <= x==479 ? 9'd0 : x+1'b1;
            row_phase <= x==479 ? y+1'b1 : y;
            if(sof) first_row <= 1;
            if(x==479) first_row <= 0;
        end
    end
    always @(posedge clk) begin
        if(valid && keep_pair && !output_pair) first_pair <= pixels[15:0];
    end
endmodule
