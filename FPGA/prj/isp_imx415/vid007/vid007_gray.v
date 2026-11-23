`timescale 1ns/1ps
module vid007_gray (
    input wire clk, rst_n,
    input wire valid, sof, eol, frame_done, frame_good,
    input wire [39:0] raw10,
    input wire full,
    output wire push,
    output wire [8:0] data
);
    // Average four pixels from each of two consecutive Bayer rows.
    reg [9:0] line_sum [0:479];
    wire [9:0] pair0 = {2'b0, raw10[9:2]} + {2'b0, raw10[19:12]};
    wire [9:0] pair1 = {2'b0, raw10[29:22]} + {2'b0, raw10[39:32]};
    wire [9:0] sum = pair0 + pair1;
    reg [8:0] x;
    reg [10:0] y;
    reg active, malformed, trailer, trailer_good;
    reg pixel_valid;
    reg [9:0] above, below;
    wire [8:0] column = sof ? 9'd0 : x;
    wire [10:0] row = sof ? 11'd0 : y;
    wire accept = valid && (sof ? !active && !trailer : active);
    wire [10:0] mixed = {1'b0, above} + {1'b0, below};
    assign push = !full && (pixel_valid || trailer);
    assign data = pixel_valid ? {1'b0, mixed[10:3]} :
                              {1'b1, trailer_good ? 8'hA5 : 8'h00};

    always @(posedge clk) begin
        if (accept && column < 480 && row < 1080) begin
            if (row[1:0] == 0)
                line_sum[column] <= sum;
            if (row[1:0] == 1) begin
                above <= line_sum[column];
                below <= sum;
            end
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            x <= 0;
            y <= 0;
            active <= 0;
            malformed <= 0;
            trailer <= 0;
            trailer_good <= 0;
            pixel_valid <= 0;
        end else begin
            pixel_valid <= accept && column < 480 && row < 1080 && row[1:0] == 1;
            if (trailer && !pixel_valid && !full)
                trailer <= 0;
            if (sof && valid) begin
                if (active) begin
                    active <= 0;
                    trailer <= 1;
                    trailer_good <= 0;
                end else if (!trailer) begin
                    active <= 1;
                    malformed <= 0;
                end
            end
            if (accept) begin
                x <= eol ? 9'd0 : column + 1'b1;
                y <= eol ? row + 1'b1 : row;
                if (eol != (column == 479) || row >= 1080)
                    malformed <= 1;
            end
            if (pixel_valid && full)
                malformed <= 1;
            if (frame_done && active) begin
                active <= 0;
                trailer <= 1;
                trailer_good <= frame_good && !malformed && y == 1080 && x == 0 &&
                                !(pixel_valid && full);
            end
        end
    end
endmodule
