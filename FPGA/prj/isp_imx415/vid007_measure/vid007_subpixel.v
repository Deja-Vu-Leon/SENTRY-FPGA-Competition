`timescale 1ns/1ps

// Find the strongest positive or negative horizontal step in the central ROI.
// Fit a parabola around the gradient peak and report x in units of 1/16 pixel.
module vid007_subpixel (
    input wire clk, reset_n, enable, valid, sof, eol, done, good,
    input wire [31:0] pixels,
    input wire [7:0] threshold,
    output reg [31:0] result
);
    reg [8:0] x;
    reg [10:0] y;
    reg [7:0] previous_pixel;
    wire [8:0] col=sof?9'd0:x;
    wire [10:0] row=sof?11'd0:y;
    function [7:0] gradient;
        input [7:0] a,b;
        begin gradient=a>b ? a-b : b-a; end
    endfunction
    reg [31:0] gradients;
    reg [8:0] col1;
    reg [10:0] row1,row2;
    reg [10:0] x2a,x2b;
    reg valid1,valid2;
    reg [7:0] a2,b2,ga_l,ga_r,gb_l,gb_r;
    wire [7:0] left=gradients[7:0], middle1=gradients[15:8];
    wire [7:0] middle2=gradients[23:16], right=gradients[31:24];
    wire peak1=middle1>left && middle1>=middle2;
    wire peak2=middle2>middle1 && middle2>=right;
    wire use_a=a2>=b2;
    wire [7:0] center=use_a?a2:b2;
    wire [7:0] before_peak=use_a?ga_l:gb_l, after_peak=use_a?ga_r:gb_r;
    reg [7:0] best;
    reg [10:0] best_x,best_y;
    reg [7:0] best_before,best_after;
    reg [11:0] numerator;
    reg [9:0] divisor;
    reg [3:0] quotient;
    reg [3:0] cycles;
    reg [10:0] x_result,y_result;
    reg negative;
    wire [11:0] fit_divisor={2'b0,divisor}<<(cycles-1'b1);
    wire next_digit=numerator>=fit_divisor;
    wire [3:0] fraction={quotient[2:0],next_digit};
    // A difference sample lies midway between the two contributing pixels.
    wire [14:0] x_grid={x_result,4'b0}-15'd8;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            x<=0; y<=0; valid1<=0; valid2<=0; best<=0; best_x<=0; best_y<=0;
            best_before<=0; best_after<=0; numerator<=0; divisor<=0;
            quotient<=0; cycles<=0; x_result<=0; y_result<=0; negative<=0; result<=0;
        end else begin
            valid1<=enable && valid && col>=120 && col<360 && row>=270 && row<810;
            valid2<=valid1;
            if(valid) begin
                x<=eol?0:col+1'b1;
                y<=eol?row+1'b1:row;
            end
            if(sof && valid) best<=0;
            else if(valid2 && center>best) begin
                best<=center; best_x<=use_a?x2a:x2b; best_y<=row2;
                best_before<=before_peak; best_after<=after_peak;
            end
            if(done && enable) begin
                if(good && best!=0 && best>=threshold) begin
                    numerator<=best_after>=best_before ? {1'b0,best_after-best_before,3'b0} :
                                                         {1'b0,best_before-best_after,3'b0};
                    divisor<={1'b0,best,1'b0}-{2'b0,best_before}-{2'b0,best_after};
                    negative<=best_after<best_before;
                    quotient<=0; cycles<=4; x_result<=best_x; y_result<=best_y;
                end else result<=0;
            end else if(cycles!=0) begin
                if(next_digit) numerator<=numerator-fit_divisor;
                quotient<=fraction; cycles<=cycles-1'b1;
                if(cycles==1) result<={1'b1,5'b0,y_result,
                    (negative ? x_grid-{11'b0,fraction} : x_grid+{11'b0,fraction})};
            end
        end
    end
    always @(posedge clk) begin
        if(valid) begin
            previous_pixel<=pixels[31:24];
            col1<=col; row1<=row;
            gradients<={gradient(pixels[31:24],pixels[23:16]),gradient(pixels[23:16],pixels[15:8]),
                        gradient(pixels[15:8],pixels[7:0]),gradient(pixels[7:0],previous_pixel)};
        end
        a2<=peak1?middle1:0; b2<=peak2?middle2:0;
        ga_l<=left; ga_r<=middle2; gb_l<=middle1; gb_r<=right;
        x2a<={col1,2'b01}; x2b<={col1,2'b10}; row2<=row1;
    end
endmodule
