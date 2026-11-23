`timescale 1ns/1ps

// Each input beat describes four pixels. At most eight bytes emerge before
// stuffing, or sixteen after stuffing. Bytes are emitted least significant first.
// The caller supplies SOI/header and EOI and buffers complete output beats.
module vid007_jpeg_entropy (
    input wire clk, reset_n, valid, sof, eof,
    input wire [51:0] code,
    input wire [5:0] bits,
    output reg out_valid, out_sof, out_eof,
    output reg [127:0] payload,
    output reg [4:0] byte_count
);
    reg [6:0] remainder;
    reg [2:0] remainder_bits;
    wire [2:0] pending=sof?3'd0:remainder_bits;
    wire [6:0] length={4'd0,pending}+{1'b0,bits};
    wire [2:0] tail=length[2:0];
    wire [2:0] pad=eof ? (3'd0-tail) : 0;
    wire [6:0] total=length+{4'd0,pad};
    wire [63:0] joined=({57'd0,(sof?7'd0:remainder)}<<bits)|{12'd0,code};
    wire [6:0] remainder_mask=~(7'h7f<<tail);
    reg [63:0] joined_q;
    reg [6:0] total_q;
    reg [2:0] pad_q;
    wire [6:0] pad_mask=~(7'h7f<<pad_q);
    wire [63:0] lined=((joined_q<<pad_q)|{57'd0,pad_mask})<<(7'd64-total_q);
    reg [63:0] bytes;
    reg [3:0] count;
    reg [2:0] tags [0:3];
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            remainder<=0; remainder_bits<=0; tags[0]<=0; tags[1]<=0; tags[2]<=0; tags[3]<=0;
            out_valid<=0; out_sof<=0; out_eof<=0;
        end else begin
            if(valid) begin
                remainder<=joined[6:0]&remainder_mask;
                remainder_bits<=eof?3'd0:tail;
            end
            tags[0]<={valid,sof,eof};
            tags[1]<=tags[0]; tags[2]<=tags[1]; tags[3]<=tags[2];
            {out_valid,out_sof,out_eof}<=tags[3];
        end
    end
    wire [15:0] item [0:7];
    wire [1:0] size [0:7];
    reg [31:0] pairs [0:3];
    reg [2:0] pair_size [0:3];
    reg [63:0] halves [0:1];
    reg [3:0] half_size [0:1];
    genvar i;
    generate for(i=0;i<8;i=i+1) begin : stuff_byte
        wire [7:0] value=bytes[63-8*i-:8];
        assign item[i]=i<count?{8'd0,value}:0;
        assign size[i]=i>=count?0:value==8'hff ? 2'd2 : 2'd1;
    end endgenerate
    integer j;
    always @(posedge clk) begin
        joined_q<=joined;
        total_q<=total;
        pad_q<=pad;
        bytes<=lined;
        count<=total_q[6:3];
        for(j=0;j<4;j=j+1) begin
            pairs[j]<={16'd0,item[2*j]}|({16'd0,item[2*j+1]}<<{size[2*j],3'b0});
            pair_size[j]<={1'b0,size[2*j]}+size[2*j+1];
        end
        for(j=0;j<2;j=j+1) begin
            halves[j]<={32'd0,pairs[2*j]}|({32'd0,pairs[2*j+1]}<<{pair_size[2*j],3'b0});
            half_size[j]<={1'b0,pair_size[2*j]}+pair_size[2*j+1];
        end
        payload<={64'd0,halves[0]}|({64'd0,halves[1]}<<{half_size[0],3'b0});
        byte_count<={1'b0,half_size[0]}+half_size[1];
    end
endmodule
