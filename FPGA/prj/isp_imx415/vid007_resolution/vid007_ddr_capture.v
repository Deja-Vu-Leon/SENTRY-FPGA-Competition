`timescale 1ns/1ps

// Collect 4 Bayer8 pixels per camera clock. Reserve a full chunk before
// accepting any of its pixels so a stalled DDR writer never corrupts a chunk.
module vid007_ddr_capture #(
    parameter AW = 11,
    parameter SKIP = 6
)(
    input wire clk, reset_n, valid, sof, done, good,
    input wire [31:0] pixels,
    input wire [1:0] resolution,
    input wire dclk, dreset_n,
    input wire pop, pop_desc,
    output wire [127:0] data,
    output wire [25:0] desc,
    output wire have_desc
);
    reg [15:0] frame;
    reg [2:0] cadence;
    reg active, failed;
    reg [8:0] chunk;
    reg [7:0] words;
    reg [1:0] lane;
    reg [95:0] partial;
    reg [19:0] pixels4;
    wire [19:0] frame_groups = resolution == 1 ? 20'd129600 : resolution == 2 ? 20'd32400 : 20'd518400;
    wire [8:0] frame_chunks = resolution == 1 ? 9'd127 : resolution == 2 ? 9'd31 : 9'd508;
    wire [7:0] frame_tail = resolution == 1 ? 8'd15 : resolution == 2 ? 8'd195 : 8'd60;
    reg report;
    reg [25:0] report_data;
    wire [AW:0] used;
    wire desc_full;
    wire [5:0] desc_fill;
    wire room = used <= (1 << AW) - 256 && !desc_full;
    wire selected = resolution != 0 || cadence != SKIP - 1;
    wire start = valid && sof && selected && room;
    wire chunk_room = words != 0 || lane != 0 || room;
    wire take = start || (valid && !sof && active && !failed && chunk_room);
    wire push_data = take && !sof && lane == 3;
    wire [5:0] desc_ready;
    assign have_desc = desc_ready != 0;
    pad_afifo #(.DW(128), .AW(AW)) u_data (
        .wclk(clk), .wrst_n(reset_n), .wr_en(push_data), .din({pixels, partial}),
        .full(), .wr_used(used), .wr_lost(), .rclk(dclk), .rrst_n(dreset_n),
        .rd_en(pop), .dout(data), .rd_avail()
    );
    pad_afifo #(.DW(26), .AW(5)) u_desc (
        .wclk(clk), .wrst_n(reset_n), .wr_en(report), .din(report_data),
        .full(), .wr_used(desc_fill), .wr_lost(), .rclk(dclk), .rrst_n(dreset_n),
        .rd_en(pop_desc), .dout(desc), .rd_avail(desc_ready)
    );
    // At most one descriptor is registered ahead of the FIFO. Reserve room
    // for both the current chunk and an end-of-frame marker.
    assign desc_full = desc_fill > 29;

    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            frame <= 16'hffff;
            cadence <= 0;
            active <= 0;
            failed <= 0;
            chunk <= 0;
            words <= 0;
            lane <= 0;
            partial <= 0;
            pixels4 <= 0;
            report <= 0;
            report_data <= 0;
        end else begin
            report <= 0;
            if (valid && sof) begin
                frame <= frame + 1'b1;
                cadence <= selected ? cadence + 1'b1 : 0;
                active <= start;
                failed <= 0;
                chunk <= 0;
                words <= 0;
                lane <= start ? 2'd1 : 2'd0;
                partial[31:0] <= pixels;
                pixels4 <= start ? 20'd1 : 20'd0;
                if (active) begin
                    report <= 1;
                    report_data <= {frame, 2'b10, words};
                end
            end else if (active) begin
                if (valid && !chunk_room)
                    failed <= 1;
                if (take) begin
                    pixels4 <= pixels4 + 1'b1;
                    lane <= lane + 1'b1;
                    case (lane)
                        0: partial[31:0] <= pixels;
                        1: partial[63:32] <= pixels;
                        2: partial[95:64] <= pixels;
                        3: begin
                            if (words == 8'd254) begin
                                report <= 1;
                                report_data <= {frame, 2'b00, 8'd255};
                                words <= 0;
                                chunk <= chunk + 1'b1;
                            end else words <= words + 1'b1;
                        end
                    endcase
                end
                if (done) begin
                    active <= 0;
                    report <= 1;
                    report_data <= {frame, 1'b1,
                                    (good && !failed && pixels4 == frame_groups &&
                                     chunk == frame_chunks && words == frame_tail && lane == 0),
                                    words};
                end
            end
        end
    end
endmodule
