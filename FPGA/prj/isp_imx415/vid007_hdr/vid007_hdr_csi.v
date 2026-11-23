`timescale 1ns/1ps

// DOL virtual-channel capture after CSI packet ECC/CRC validation.
// The payload is provisional until both VC frame-end trailers have completed.
module vid007_hdr_csi #(
    parameter LONG_VC=0,SHORT_VC=1,
    parameter X0=4,Y0=16,WIDTH=1920,HEIGHT=1080,
    parameter FIFO_AW=10,
    parameter COMPACT=0,LONG_AW=12,SHORT_AW=9
)(
    input wire clk,reset_n,ready,
    input wire fs,fe,line_error,
    input wire [1:0] vc,
    input wire [15:0] frame_id,
    input wire valid,first,last,raw12,
    input wire [31:0] bytes,
    input wire [2:0] length,
    input wire [2:0] exposure_shift,
    output wire out_valid,out_sof,out_eol,
    output wire [39:0] pixels,
    output reg frame_done,frame_good,
    output wire [31:0] lost_pairs,
    output reg [127:0] status
);
    wire reset_capture=reset_n && ready;
    wire [1:0] start={fs && vc==SHORT_VC,fs && vc==LONG_VC};
    wire [1:0] stop={fe && vc==SHORT_VC,fe && vc==LONG_VC};
    wire [1:0] pixel_valid,pixel_sof,pixel_eol,malformed;
    wire [39:0] raster [0:1];
    wire [10:0] rows [0:1];
    reg [15:0] frame_sequence [0:1];
    reg [1:0] opened,ended,bad;
    reg pair_open;
    reg [15:0] pair_id;
    wire new_pair=(|start) && (!pair_open || frame_id!=pair_id);
    wire pair_failed;
    genvar ch;
    generate for(ch=0;ch<2;ch=ch+1) begin : exposure
        localparam THIS_VC=ch==0?LONG_VC:SHORT_VC;
        vid007_hdr_raw12 #(.X0(X0),.Y0(Y0),.WIDTH(WIDTH),.HEIGHT(HEIGHT)) capture (
            .clk(clk),.reset_n(reset_capture),.frame_start(start[ch]),.frame_end(stop[ch]),
            .valid(valid && vc==THIS_VC),.first(first),.last(last),.raw12(raw12),.bytes(bytes),.length(length),
            .out_valid(pixel_valid[ch]),.out_sof(pixel_sof[ch]),.out_eol(pixel_eol[ch]),
            .pixels(raster[ch]),.invalid_frame(malformed[ch]),.received_rows(rows[ch])
        );
    end endgenerate
    generate if(COMPACT) begin : compact_pair
        vid007_hdr_pair_compact #(.LONG_AW(LONG_AW),.SHORT_AW(SHORT_AW),.WIDTH(WIDTH)) pair (
            .clk(clk),.reset_n(reset_capture),.clear(new_pair),
            .long_valid(pixel_valid[0]),.long_pixels(raster[0]),.short_valid(pixel_valid[1]),.short_pixels(raster[1]),
            .exposure_shift(exposure_shift),.valid(out_valid),.sof(out_sof),.eol(out_eol),
            .pixels(pixels),.lost_pairs(lost_pairs),.failed(pair_failed)
        );
    end else begin : tagged_pair
        assign pair_failed=0;
        vid007_hdr_pair #(.AW(FIFO_AW)) pair (
            .clk(clk),.reset_n(reset_capture),.long_valid(pixel_valid[0]),.long_sof(pixel_sof[0]),.long_eol(pixel_eol[0]),
            .long_frame(frame_sequence[0]),.long_pixels(raster[0]),.short_valid(pixel_valid[1]),
            .short_sof(pixel_sof[1]),.short_eol(pixel_eol[1]),.short_frame(frame_sequence[1]),.short_pixels(raster[1]),
            .exposure_shift(exposure_shift),.valid(out_valid),.sof(out_sof),.eol(out_eol),.pixels(pixels),.lost_pairs(lost_pairs)
        );
    end endgenerate
    reg [19:0] count;
    reg [31:0] baseline_lost;
    reg [3:0] settle;
    integer i;
    always @(posedge clk or negedge reset_capture) begin
        if(!reset_capture) begin
            frame_sequence[0]<=0; frame_sequence[1]<=0; opened<=0; ended<=0; bad<=0;
            frame_done<=0; frame_good<=0; count<=0; baseline_lost<=0; settle<=0;
            status<=0; pair_open<=0; pair_id<=0;
        end else if(new_pair) begin
            frame_done<=0; frame_good<=0; count<=0; baseline_lost<=lost_pairs; settle<=0;
            pair_open<=1; pair_id<=frame_id;
            opened<=start; ended<=0; bad<=0;
            if(start[0]) frame_sequence[0]<=frame_id;
            if(start[1]) frame_sequence[1]<=frame_id;
        end else begin
            frame_done<=0; frame_good<=0;
            if(out_valid) begin
                count<=out_sof?20'd1:count+1'b1;
                if(out_sof) baseline_lost<=lost_pairs;
            end
            for(i=0;i<2;i=i+1) begin
                if(start[i]) begin
                    frame_sequence[i]<=frame_id; opened[i]<=1; ended[i]<=0; bad[i]<=0;
                end else if(opened[i]) begin
                    if(stop[i]) begin ended[i]<=1; opened[i]<=0; end
                    if(line_error && vc==(i==0?LONG_VC:SHORT_VC)) bad[i]<=1;
                end
            end
            if(&ended && settle==0) settle<=8;
            else if(settle!=0) begin
                settle<=settle-1'b1;
                if(settle==1) begin
                    frame_done<=1;
                    frame_good<=!pair_failed && !(|bad) && !(|malformed) && frame_sequence[0]==frame_sequence[1] &&
                                count==WIDTH*HEIGHT/4 && lost_pairs==baseline_lost;
                    ended<=0; pair_open<=0;
                    status<={frame_sequence[1],frame_sequence[0],
                             10'd0,rows[1],rows[0],
                             6'd0,pair_failed,frame_sequence[0]==frame_sequence[1],bad,malformed,count,
                             lost_pairs-baseline_lost};
                end
            end
        end
    end
endmodule
