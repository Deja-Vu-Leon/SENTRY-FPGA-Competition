`timescale 1ns/1ps

// One exposure's line unpacker. VC demultiplexing is before this component.
// CSI RAW12 packs two high bytes, followed by the two low nibbles. The fusion
// path uses RAW10, so drop two least-significant bits from each input sample.
module vid007_hdr_raw12 #(
    parameter X0=4, Y0=16, WIDTH=1920, HEIGHT=1080
)(
    input wire clk,reset_n,
    input wire frame_start,frame_end,valid,first,last,
    input wire raw12,
    input wire [31:0] bytes,
    input wire [2:0] length,
    output reg out_valid,out_sof,out_eol,
    output reg [39:0] pixels,
    output reg invalid_frame,
    output wire [10:0] received_rows
);
    reg frame_open,line_open;
    reg [10:0] row;
    reg [9:0] group;
    reg [39:0] carry;
    reg [2:0] count;
    assign received_rows=row;
    wire [2:0] cached=first?3'd0:count;
    wire [3:0] available={1'b0,cached}+{1'b0,length};
    wire [3:0] group_bytes=raw12?4'd6:4'd5;
    wire [9:0] column=first?10'd0:group;
    wire [31:0] mask=32'hffffffff>>((4-length)*8);
    wire [71:0] value=(first?72'd0:{32'd0,carry})|({40'd0,bytes&mask}<<(cached*8));
    function [39:0] unpack;
        input [47:0] data;
        begin unpack={data[39:32],data[47:46],data[31:24],data[43:42],
                      data[15:8],data[23:22],data[7:0],data[19:18]}; end
    endfunction
    wire first_active=column==X0/4;
    wire last_active=column==(X0+WIDTH)/4-1;
    wire inside_crop=row>=Y0 && row<Y0+HEIGHT && column>=X0/4 && column<(X0+WIDTH)/4;

    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            frame_open<=0; line_open<=0; row<=0; group<=0; carry<=0; count<=0;
            out_valid<=0; out_sof<=0; out_eol<=0; pixels<=0; invalid_frame<=0;
        end else begin
            out_valid<=0; out_sof<=0; out_eol<=0;
            if(frame_start) begin
                frame_open<=1; line_open<=0; row<=0; group<=0; carry<=0; count<=0; invalid_frame<=0;
            end else if(frame_end) begin
                frame_open<=0;
                if(line_open || row<Y0+HEIGHT) invalid_frame<=1;
            end else if(valid && frame_open) begin
                if(first==line_open || length==0 || length>4) invalid_frame<=1;
                line_open<=!last;
                if(available>=group_bytes) begin
                    if(inside_crop && !invalid_frame) begin
                        out_valid<=1;
                        out_sof<=first_active && row==Y0;
                        out_eol<=last_active;
                        pixels<=raw12?unpack(value[47:0]):
                            {value[31:24],value[39:38],value[23:16],value[37:36],
                             value[15:8],value[35:34],value[7:0],value[33:32]};
                    end
                    count<=available-group_bytes;
                    carry<=raw12?{16'd0,value[71:48]}:{8'd0,value[71:40]};
                    group<=column+1'b1;
                end else begin count<=available[2:0]; carry<=value[39:0]; group<=column; end
                if(last) begin
                    if(available!=group_bytes || column<(X0+WIDTH)/4-1) invalid_frame<=1;
                    row<=row+1'b1; count<=0; carry<=0; group<=0;
                end
            end
        end
    end
endmodule
