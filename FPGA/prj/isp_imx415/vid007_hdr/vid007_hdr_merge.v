`timescale 1ns/1ps

// Fuse co-registered RAW10 long and short samples. Both sequences must be
// supplied by the sensor receiver and identified with the same frame and line.
module vid007_hdr_merge (
    input wire clk, reset_n, valid, sof, eol,
    input wire [39:0] long_pixels, short_pixels,
    input wire [2:0] exposure_shift,
    output reg out_valid, out_sof, out_eol,
    output wire [39:0] fused_pixels
);
    reg [1:0] vt, st, et;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            vt<=0; st<=0; et<=0;
            out_valid<=0; out_sof<=0; out_eol<=0;
        end else begin
            vt<={vt[0],valid}; st<={st[0],sof}; et<={et[0],eol};
            out_valid<=vt[1]; out_sof<=st[1]; out_eol<=et[1];
        end
    end
    genvar lane;
    generate for(lane=0;lane<4;lane=lane+1) begin : pixels
        wire [9:0] long_sample=long_pixels[lane*10+:10];
        wire [9:0] short_sample=short_pixels[lane*10+:10];
        // Subtract the sensor's 10-bit black pedestal before exposure scaling.
        wire [9:0] short_scene=short_sample>64?short_sample-10'd64:0;
        reg [16:0] scaled;
        reg [9:0] long_q;
        reg [17:0] radiance;
        reg [9:0] mapped;
        wire [17:0] long_scene=long_q>64?{8'd0,long_q}-18'd64:0;
        wire [17:0] short_radiance={1'b0,scaled};
        wire [17:0] shoulder=(radiance-18'd768)>>3;
        always @(posedge clk) begin
            scaled<={7'd0,short_scene}<<exposure_shift;
            long_q<=long_sample;
            if(long_q<832) radiance<=long_scene;
            else if(long_q<960) radiance<=(long_scene+short_radiance)>>1;
            else radiance<=short_radiance;
            if(radiance<768) mapped<=radiance[9:0];
            else mapped<=shoulder>255?10'd1023:10'd768+shoulder[9:0];
        end
        assign fused_pixels[lane*10+:10]=mapped;
    end endgenerate
endmodule
