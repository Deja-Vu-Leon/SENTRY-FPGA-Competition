`timescale 1ns/1ps

// Turn variable-length scan beats into blocks for the existing DDR capture.
// The last 16-byte word is zero-padded. The host uses the byte length, not
// the padding, when constructing the JPEG packet.
module vid007_jpeg_blocks (
    input wire clk, reset_n, valid, sof, eof,
    input wire [127:0] payload,
    input wire [4:0] byte_count,
    output reg block_valid, block_sof, block_last,
    output reg [127:0] block,
    output reg [21:0] frame_bytes
);
    reg [127:0] tail;
    reg [3:0] fill;
    reg [21:0] length;
    reg first, flush;
    wire [3:0] used=sof?4'd0:fill;
    wire [4:0] bytes_to_fill=5'd16-{1'b0,used};
    wire [4:0] remaining=byte_count-bytes_to_fill;
    wire [127:0] low=(sof?128'd0:tail)|(payload<<{used,3'b0});
    wire [127:0] high=payload>>{bytes_to_fill,3'b0};
    wire [21:0] length_next=(sof?22'd0:length)+{17'd0,byte_count};
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            tail<=0; fill<=0; first<=1; length<=0; flush<=0;
            block_valid<=0; block_sof<=0; block_last<=0; block<=0; frame_bytes<=0;
        end else begin
            block_valid<=0; block_sof<=0; block_last<=0;
            if(flush) begin
                block_valid<=1; block_last<=1; block_sof<=first; block<=tail;
                flush<=0; fill<=0; tail<=0; first<=1;
            end else if(valid) begin
                length<=length_next;
                if(sof) first<=1;
                if(byte_count>=bytes_to_fill) begin
                    block_valid<=1; block_sof<=sof||first; block<=low; first<=0;
                    tail<=high; fill<=remaining[3:0];
                    if(eof) begin
                        if(remaining==0) block_last<=1;
                        else flush<=1;
                    end
                end else if(eof) begin
                    block_valid<=1; block_sof<=sof||first; block_last<=1; block<=low;
                    fill<=0; tail<=0; first<=1;
                end else begin
                    tail<=low; fill<=used+byte_count[3:0];
                end
                if(eof) frame_bytes<=length_next;
            end
        end
    end
endmodule
