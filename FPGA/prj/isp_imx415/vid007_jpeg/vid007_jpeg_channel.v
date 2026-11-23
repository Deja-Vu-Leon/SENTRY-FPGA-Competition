`timescale 1ns/1ps

// The receiver guarantees a quiescent interval between camera frames.
module vid007_jpeg_channel (
    input wire clk, reset_n, valid, sof,
    input wire [31:0] pixels,
    input wire [1:0] resolution,
    input wire [1:0] codec,
    input wire [7:0] target_kib,
    output wire ready_block, first_block, last_block,
    output wire [127:0] block,
    output wire [21:0] scan_bytes,
    output wire [2:0] actual_transform
);
    reg [8:0] x;
    reg [10:0] y;
    wire [8:0] col=sof?9'd0:x;
    wire [10:0] row=sof?11'd0:y;
    wire at_eol=col==(resolution==1?9'd239:resolution==2?9'd119:9'd479);
    wire at_eof=at_eol && row==(resolution==1?11'd539:resolution==2?11'd269:11'd1079);
    // Register is expressed in 16 KiB units so targets above the 1080p
    // entropy floor (one bit/pixel for this Huffman table) are representable.
    wire [21:0] target_bytes={target_kib,14'd0};
    reg [2:0] adaptive_transform, frame_transform;
    reg started;
    wire [2:0] transform=sof ? (codec==1?3'd0:adaptive_transform) : frame_transform;
    assign actual_transform=frame_transform;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin x<=0; y<=0; adaptive_transform<=1; frame_transform<=0; started<=0; end
        else begin
            if(valid) begin
                x<=at_eol?9'd0:col+1'b1;
                y<=at_eol?row+1'b1:row;
                if(sof) frame_transform<=transform;
            end
            if(ready_block && last_block && codec==2) begin
                started<=1;
                if(scan_bytes>target_bytes && adaptive_transform<7) adaptive_transform<=adaptive_transform+1'b1;
                else if(started && scan_bytes<target_bytes-(target_bytes>>3) && adaptive_transform>1)
                    adaptive_transform<=adaptive_transform-1'b1;
            end
        end
    end
    wire pred_valid,pred_sof,pred_eof;
    wire [51:0] code;
    wire [5:0] bits;
    vid007_jpeg_predict prediction (
        .clk(clk),.reset_n(reset_n),.valid(valid && codec!=0),.sof(valid && sof),.eol(at_eol),.eof(valid && at_eof),
        .pixels(pixels),.point_transform(transform),.valid_q(pred_valid),.sof_q(pred_sof),.eof_q(pred_eof),.code(code),.bits(bits)
    );
    wire entropy_valid,entropy_sof,entropy_eof;
    wire [127:0] payload;
    wire [4:0] byte_count;
    vid007_jpeg_entropy entropy (
        .clk(clk),.reset_n(reset_n),.valid(pred_valid),.sof(pred_sof),.eof(pred_eof),.code(code),.bits(bits),
        .out_valid(entropy_valid),.out_sof(entropy_sof),.out_eof(entropy_eof),.payload(payload),.byte_count(byte_count)
    );
    vid007_jpeg_blocks pack (
        .clk(clk),.reset_n(reset_n),.valid(entropy_valid),.sof(entropy_sof),.eof(entropy_eof),
        .payload(payload),.byte_count(byte_count),.block_valid(ready_block),.block_sof(first_block),
        .block_last(last_block),.block(block),.frame_bytes(scan_bytes)
    );
endmodule
