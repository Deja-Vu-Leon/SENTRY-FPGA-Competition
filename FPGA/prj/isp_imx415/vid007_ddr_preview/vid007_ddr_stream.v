`timescale 1ns/1ps
module vid007_ddr_stream (
    input wire cam_clk, cam_reset_n,
    input wire [3:0] valid, sof, done, good,
    input wire [127:0] pixels,
    input wire dclk, dreset_n,
    output wire [29:0] waddr, raddr,
    output wire [15:0] wsize, rsize,
    output wire wreq, rreq,
    input wire wbusy, wvalid, rbusy, rvalid,
    output wire [127:0] wdata,
    input wire [127:0] rdata,
    input wire user_clk, user_reset_n,
    input wire [2:0] mode,
    output wire [127:0] tdata,
    output wire [15:0] tkeep,
    output wire tlast, tvalid,
    input wire tready
);
    wire [127:0] input_data [0:3];
    wire [25:0] input_desc [0:3];
    wire [3:0] have, pop_data, pop_desc;
    localparam SKIP = 6;
    genvar g;
    generate for (g=0; g<4; g=g+1) begin : camera
        vid007_ddr_capture #(.SKIP(SKIP)) u_capture (
            .clk(cam_clk), .reset_n(cam_reset_n), .valid(valid[g]), .sof(sof[g]),
            .done(done[g]), .good(good[g]), .pixels(pixels[g*32+:32]),
            .dclk(dclk), .dreset_n(dreset_n), .pop(pop_data[g]), .pop_desc(pop_desc[g]),
            .data(input_data[g]), .desc(input_desc[g]), .have_desc(have[g])
        );
    end endgenerate

    // Each camera owns eight 2 MiB slots. Publish only complete frames.
    // The write cursor may fill a slot until its final DDR write completes.
    reg [3:0] write_slot [0:3], read_slot [0:3];
    reg [15:0] frame_id [0:31];
    reg [8:0] write_chunk [0:3];
    reg [1:0] wc, rc;
    reg [8:0] read_chunk;
    localparam W_SCAN = 0, W_REQ = 1, W_WAIT = 2, W_DROP = 3;
    reg [1:0] ws;
    reg [7:0] remaining;
    wire [25:0] front = input_desc[wc];
    wire [7:0] words = front[7:0];
    wire end_frame = front[9];
    wire frame_good = front[8];
    wire full = write_slot[wc] == (read_slot[wc] ^ 4'b1000);
    wire [29:0] wa = {4'b0, wc, write_slot[wc][2:0], write_chunk[wc], 12'b0};
    assign waddr = wa;
    assign wdata = input_data[wc];
    assign wsize = {8'b0, words};
    assign wreq = ws == W_REQ;
    wire write_done = ws == W_WAIT && !wbusy;
    wire drop_done = ws == W_DROP && remaining == 0;
    generate for (g=0; g<4; g=g+1) begin : consume
        assign pop_data[g] = wc == g && (((ws == W_REQ || ws == W_WAIT) && wvalid) ||
                                         (ws == W_DROP && remaining != 0));
        assign pop_desc[g] = wc == g && (write_done || drop_done);
    end endgenerate

    integer i;
    always @(posedge dclk or negedge dreset_n) begin
        if (!dreset_n) begin
            wc <= 0;
            ws <= W_SCAN;
            remaining <= 0;
            for (i=0; i<4; i=i+1) begin
                write_slot[i] <= 0;
                write_chunk[i] <= 0;
            end
        end else begin
            case (ws)
                W_SCAN: begin
                    if (!have[wc]) wc <= wc + 1'b1;
                    else if (words == 0 || (end_frame && !frame_good)) begin
                        remaining <= words;
                        ws <= W_DROP;
                    end else if (!full) ws <= W_REQ;
                    else wc <= wc + 1'b1;
                end
                W_REQ: if (wbusy) ws <= W_WAIT;
                W_WAIT: if (write_done) begin
                    if (end_frame) begin
                        write_slot[wc] <= write_slot[wc] + 1'b1;
                        write_chunk[wc] <= 0;
                    end else write_chunk[wc] <= write_chunk[wc] + 1'b1;
                    wc <= wc + 1'b1;
                    ws <= W_SCAN;
                end
                W_DROP: begin
                    if (remaining != 0) remaining <= remaining - 1'b1;
                    else begin
                        write_chunk[wc] <= 0;
                        wc <= wc + 1'b1;
                        ws <= W_SCAN;
                    end
                end
            endcase
        end
    end
    always @(posedge dclk)
        if (write_done && end_frame)
            frame_id[{wc, write_slot[wc][2:0]}] <= front[25:10];

    localparam R_SCAN = 0, R_HEADER = 1, R_REQ = 2, R_WAIT = 3, R_TRAILER = 4;
    reg [2:0] rs;
    reg [7:0] beat;
    localparam OUT_AW = 11;
    wire [OUT_AW:0] out_used, out_ready;
    wire last_chunk = read_chunk == 508;
    wire [15:0] length = last_chunk ? 16'd964 : 16'd4080;
    wire [7:0] body_words = last_chunk ? 8'd60 : 8'd255;
    wire [31:0] sequence_frame = {16'b0, frame_id[{rc, read_slot[rc][2:0]}]};
    wire [127:0] header = {sequence_frame, length, 7'b0, read_chunk,
                           6'b0, last_chunk, (read_chunk == 0), 6'b0, rc, 32'h4b4e4843};
    wire header_push = rs == R_HEADER;
    wire body_push = (rs == R_REQ || rs == R_WAIT) && rvalid;
    wire trailer_push = rs == R_TRAILER;
    wire [127:0] outgoing = header_push ? header : trailer_push ? {120'b0, 5'b10100, mode} : rdata;
    wire last = trailer_push || (body_push && !last_chunk && beat == 254);
    assign raddr = {4'b0, rc, read_slot[rc][2:0], read_chunk, 12'b0};
    assign rsize = {8'b0, body_words};
    assign rreq = rs == R_REQ;
    assign tvalid = out_ready != 0;
    wire short_beat;
    assign tkeep = short_beat ? 16'h000f : 16'hffff;

    pad_afifo #(.DW(130), .AW(OUT_AW)) u_output (
        .wclk(dclk), .wrst_n(dreset_n), .wr_en(header_push || body_push || trailer_push),
        .din({trailer_push, last, outgoing}), .full(), .wr_used(out_used), .wr_lost(),
        .rclk(user_clk), .rrst_n(user_reset_n), .rd_en(tvalid && tready),
        .dout({short_beat, tlast, tdata}), .rd_avail(out_ready)
    );

    integer j;
    always @(posedge dclk or negedge dreset_n) begin
        if (!dreset_n) begin
            rc <= 0;
            rs <= R_SCAN;
            beat <= 0;
            read_chunk <= 0;
            for (j=0; j<4; j=j+1) read_slot[j] <= 0;
        end else begin
            case (rs)
                R_SCAN: if (out_used <= (1 << OUT_AW) - 256) begin
                    if (write_slot[rc] != read_slot[rc]) rs <= R_HEADER;
                    else rc <= rc + 1'b1;
                end
                R_HEADER: begin
                    beat <= 0;
                    rs <= R_REQ;
                end
                R_REQ: if (rbusy) begin
                    if (rvalid) beat <= beat + 1'b1;
                    rs <= R_WAIT;
                end
                R_WAIT: begin
                    if (rvalid) beat <= beat + 1'b1;
                    if (!rbusy) begin
                        if (last_chunk) rs <= R_TRAILER;
                        else begin
                            read_chunk <= read_chunk + 1'b1;
                            rs <= R_HEADER;
                            if (out_used > (1 << OUT_AW) - 256) rs <= R_SCAN;
                        end
                    end
                end
                R_TRAILER: begin
                    read_slot[rc] <= read_slot[rc] + 1'b1;
                    read_chunk <= 0;
                    rc <= rc + 1'b1;
                    rs <= R_SCAN;
                end
            endcase
        end
    end
endmodule
