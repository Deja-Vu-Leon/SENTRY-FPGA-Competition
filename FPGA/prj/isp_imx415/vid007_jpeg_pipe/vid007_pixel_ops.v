`timescale 1ns/1ps

// Additional streaming operators use the same four-pixel neighborhood as Sobel.
module vid007_pixel_ops (
    input wire clk,
    input wire [47:0] top, middle, bottom,
    input wire interior,
    input wire [6:4] operation,
    input wire [7:0] level,
    output wire [31:0] pixels
);
    function [7:0] extremum;
        input [7:0] a, b, c;
        input erode;
        reg ab,ac,bc;
        begin
            ab=(a<b)==erode;
            ac=(a<c)==erode;
            bc=(b<c)==erode;
            extremum=ab && ac ? a : !ab && bc ? b : c;
        end
    endfunction

    genvar lane;
    generate for (lane=0; lane<4; lane=lane+1) begin : process_lane
        localparam P = lane*8;
        wire [7:0] sample = bottom[P+16+:8];
        wire erode = operation == 4;
        reg [7:0] a, b, c, original;
        reg [7:0] point, spatial, result;
        reg border;
        wire [7:0] distance = sample - level;
        wire [8:0] half = {1'b0,sample} + {2'b0,distance[7:1]};
        wire [7:0] headroom = ~sample;
        wire [7:0] light_lift = {1'b0,sample[7:1]} < {2'b0,headroom[7:2]} ?
                                {1'b0,sample[7:1]} : {2'b0,headroom[7:2]};

        always @(posedge clk) begin
            a <= extremum(top[P+:8],top[P+8+:8],top[P+16+:8],erode);
            b <= extremum(middle[P+:8],middle[P+8+:8],middle[P+16+:8],erode);
            c <= extremum(bottom[P+:8],bottom[P+8+:8],bottom[P+16+:8],erode);
            original <= sample;
            border <= !interior;
            spatial <= border ? original : extremum(a,b,c,erode);
            case (operation)
                2: point <= sample >= level ? 8'hff : 0;
                // Single-exposure dynamic range mapping: lift dark tones and
                // roll the curve into the highlight ceiling. Level caps the lift.
                5: point <= sample + (light_lift < level ? light_lift : level);
                // Fixed-airlight dehaze: subtract the configurable veil and
                // restore midtone contrast with an inexpensive fixed gain.
                6: point <= sample <= level ? 8'd0 : half[8] ? 8'hff : half[7:0];
                default: point <= sample;
            endcase
        end
        reg [7:0] point_q;
        always @(posedge clk) begin
            point_q <= point;
            result <= (operation == 3 || operation == 4) ? spatial : point_q;
        end
        assign pixels[P+:8] = result;
    end endgenerate
endmodule
