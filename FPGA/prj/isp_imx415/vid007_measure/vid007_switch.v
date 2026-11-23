`timescale 1ns/1ps

// Four pixels per clock. Synchronous line stores provide the previous two rows;
// each 48-bit row is {four current pixels, two pixels from the preceding beat}.
module vid007_window4 (
    input wire clk, rst_n, valid, sof, eol,
    input wire [31:0] pixels,
    output reg valid_q, sof_q, eol_q,
    output wire [47:0] top, mid, bot,
    output wire first,
    output reg [10:0] row_q
);
    reg [31:0] bank0 [0:479];
    reg [31:0] bank1 [0:479];
    reg [31:0] from0, from1, current_q;
    reg [8:0] x, x_q;
    reg [10:0] y;
    wire [8:0] column = sof ? 9'd0 : x;
    wire [10:0] row = sof ? 11'd0 : y;
    wire [31:0] top_word = row_q[0] ? from1 : from0;
    wire [31:0] mid_word = row_q[0] ? from0 : from1;
    reg [15:0] left_top, left_mid, left_bot;
    assign first = x_q == 0;
    assign top = {top_word, first ? 16'b0 : left_top};
    assign mid = {mid_word, first ? 16'b0 : left_mid};
    assign bot = {current_q, first ? 16'b0 : left_bot};

    always @(posedge clk) begin
        if (valid && column < 480) begin
            from0 <= bank0[column];
            from1 <= bank1[column];
            current_q <= pixels;
            x_q <= column;
            row_q <= row;
        end
        if (valid_q) begin
            if (row_q[0]) bank1[x_q] <= current_q;
            else          bank0[x_q] <= current_q;
            left_top <= top_word[31:16];
            left_mid <= mid_word[31:16];
            left_bot <= current_q[31:16];
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            x <= 0;
            y <= 0;
            valid_q <= 0;
            sof_q <= 0;
            eol_q <= 0;
        end else begin
            valid_q <= valid && column < 480;
            sof_q <= sof;
            eol_q <= eol;
            if (valid) begin
                x <= eol ? 9'd0 : column + 1'b1;
                y <= eol ? row + 1'b1 : row;
            end
        end
    end
endmodule

module vid007_color_window4 (
    input wire clk, rst_n, valid, sof, eol,
    input wire [31:0] pixels,
    output reg valid_q, sof_q, eol_q,
    output wire [63:0] top, mid, bot,
    output wire first,
    output reg [10:0] row_q
);
    reg [31:0] bank0 [0:1023];
    reg [31:0] bank1 [0:1023];
    reg [31:0] from0, from1, current_q;
    reg [8:0] x, x_q;
    reg [10:0] y;
    wire [8:0] column = sof ? 9'd0 : x;
    wire [10:0] row = sof ? 11'd0 : y;
    wire [31:0] top_word = row_q[1] ? from1 : from0;
    wire [31:0] mid_word = row_q[1] ? from0 : from1;
    reg [31:0] left_top, left_mid, left_bot;
    assign first = x_q == 0;
    assign top = {top_word, first ? 32'b0 : left_top};
    assign mid = {mid_word, first ? 32'b0 : left_mid};
    assign bot = {current_q, first ? 32'b0 : left_bot};

    always @(posedge clk) begin
        if (valid && column < 480) begin
            from0 <= bank0[{row[0], column}];
            from1 <= bank1[{row[0], column}];
            current_q <= pixels;
            x_q <= column;
            row_q <= row;
        end
        if (valid_q) begin
            if (row_q[1]) bank1[{row_q[0], x_q}] <= current_q;
            else          bank0[{row_q[0], x_q}] <= current_q;
            left_top <= top_word;
            left_mid <= mid_word;
            left_bot <= current_q;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            x <= 0;
            y <= 0;
            valid_q <= 0;
            sof_q <= 0;
            eol_q <= 0;
        end else begin
            valid_q <= valid && column < 480;
            sof_q <= sof;
            eol_q <= eol;
            if (valid) begin
                x <= eol ? 9'd0 : column + 1'b1;
                y <= eol ? row + 1'b1 : row;
            end
        end
    end
endmodule

module vid007_switch #(
    parameter EXTENSIONS = 0
) (
    input wire clk, rst_n,
    input wire valid, sof, eol, frame_done, frame_good,
    input wire [39:0] raw10,
    input wire full,
    input wire [2:0] mode,
    input wire extended,
    input wire [6:4] operation,
    input wire [7:0] level,
    output wire preview_valid, preview_sof, preview_done, preview_good,
    output wire [31:0] preview_pixels,
    output wire [31:0] feature_result,
    output wire push,
    output wire [8:0] data
);
    wire extension_active = EXTENSIONS && extended;
    wire [10:0] sobel_threshold = extension_active ? {3'b0,level} : 11'd80;
    wire grayscale = mode[0] || (extension_active && (mode[2] || operation != 0));
    wire [31:0] raw8 = {raw10[39:32], raw10[29:22], raw10[19:12], raw10[9:2]};
    wire gray_window_valid, gray_window_sof, gray_window_eol, gray_first;
    wire [10:0] gray_row;
    wire [47:0] gray_mid, gray_bot;
    vid007_window4 u_gray_rows (
        .clk(clk), .rst_n(rst_n), .valid(valid), .sof(sof), .eol(eol), .pixels(raw8),
        .valid_q(gray_window_valid), .sof_q(gray_window_sof), .eol_q(gray_window_eol),
        .top(), .mid(gray_mid), .bot(gray_bot), .first(gray_first), .row_q(gray_row)
    );
    reg [31:0] gray;
    reg gray_valid, gray_sof, gray_eol;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) {gray_valid, gray_sof, gray_eol} <= 0;
        else {gray_valid, gray_sof, gray_eol} <= {gray_window_valid, gray_window_sof, gray_window_eol};
    end

    wire gauss_window_valid, gauss_window_sof, gauss_window_eol, gauss_first;
    wire [10:0] gauss_row;
    wire [47:0] gauss_top, gauss_mid, gauss_bot;
    vid007_window4 u_gauss_rows (
        .clk(clk), .rst_n(rst_n), .valid(gray_valid), .sof(gray_sof), .eol(gray_eol), .pixels(gray),
        .valid_q(gauss_window_valid), .sof_q(gauss_window_sof), .eol_q(gauss_window_eol),
        .top(gauss_top), .mid(gauss_mid), .bot(gauss_bot), .first(gauss_first), .row_q(gauss_row)
    );
    wire [63:0] ctop, cmid, cbot;
    vid007_color_window4 u_color_gauss_rows (
        .clk(clk), .rst_n(rst_n), .valid(gray_valid && !grayscale && mode[1]),
        .sof(gray_sof), .eol(gray_eol), .pixels(gray), .valid_q(), .sof_q(), .eol_q(),
        .top(ctop), .mid(cmid), .bot(cbot), .first(), .row_q()
    );
    reg [31:0] gaussian;
    reg [2:0] gauss_tags [0:1];
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            gauss_tags[0] <= 0;
            gauss_tags[1] <= 0;
        end else begin
            gauss_tags[0] <= {gauss_window_valid, gauss_window_sof, gauss_window_eol};
            gauss_tags[1] <= gauss_tags[0];
        end
    end

    wire sobel_window_valid, sobel_window_sof, sobel_window_eol, sobel_first;
    wire [10:0] sobel_row;
    wire [47:0] sobel_top, sobel_mid, sobel_bot;
    vid007_window4 u_sobel_rows (
        .clk(clk), .rst_n(rst_n), .valid(gauss_tags[1][2]), .sof(gauss_tags[1][1]),
        .eol(gauss_tags[1][0]), .pixels(gaussian), .valid_q(sobel_window_valid),
        .sof_q(sobel_window_sof), .eol_q(sobel_window_eol),
        .top(sobel_top), .mid(sobel_mid), .bot(sobel_bot), .first(sobel_first), .row_q(sobel_row)
    );
    reg [3:0] edge_pixels;
    reg [2:0] sobel_tags [0:2];
    reg [1:0] interior;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sobel_tags[0] <= 0;
            sobel_tags[1] <= 0;
            sobel_tags[2] <= 0;
            interior <= 0;
        end else begin
            sobel_tags[0] <= {sobel_window_valid, sobel_window_sof, sobel_window_eol};
            sobel_tags[1] <= sobel_tags[0];
            sobel_tags[2] <= sobel_tags[1];
            interior <= {interior[0], !sobel_first && sobel_row >= 4};
        end
    end

    function [9:0] weighted;
        input [7:0] a, b, c;
        begin weighted = {2'b0, a} + {1'b0, b, 1'b0} + {2'b0, c}; end
    endfunction

    genvar i;
    generate for (i = 0; i < 4; i = i + 1) begin : lanes
        localparam P = i * 8;
        // A sliding Bayer 2x2 cell always contains R/G/G/B. Estimate luma
        // without halving the raster; use the local sample at the outer border.
        wire [9:0] luma = {2'b0, gray_mid[P+8+:8]} + {2'b0, gray_mid[P+16+:8]} +
                          {2'b0, gray_bot[P+8+:8]} + {2'b0, gray_bot[P+16+:8]};
        reg [9:0] sum_top, sum_mid, sum_bot;
        reg gauss_border;
        reg [7:0] bypass_q;
        wire [11:0] gauss_sum = {2'b0, sum_top} + {1'b0, sum_mid, 1'b0} +
                                {2'b0, sum_bot} + 12'd8;
        reg [9:0] dx_hi, dx_lo, dy_hi, dy_lo;
        reg [9:0] abs_x, abs_y;
        wire [10:0] magnitude = {1'b0, abs_x} + {1'b0, abs_y};
        always @(posedge clk) begin
            gray[P+:8] <= (!grayscale || gray_row == 0 || (gray_first && i == 0)) ? gray_bot[P+16+:8] : luma[9:2];

            sum_top <= grayscale ? weighted(gauss_top[P+:8], gauss_top[P+8+:8], gauss_top[P+16+:8]) :
                                  weighted(ctop[P+:8], ctop[P+16+:8], ctop[P+32+:8]);
            sum_mid <= grayscale ? weighted(gauss_mid[P+:8], gauss_mid[P+8+:8], gauss_mid[P+16+:8]) :
                                  weighted(cmid[P+:8], cmid[P+16+:8], cmid[P+32+:8]);
            sum_bot <= grayscale ? weighted(gauss_bot[P+:8], gauss_bot[P+8+:8], gauss_bot[P+16+:8]) :
                                  weighted(cbot[P+:8], cbot[P+16+:8], cbot[P+32+:8]);
            gauss_border <= grayscale ? (gauss_row < 2 || (gauss_first && i < 2)) :
                                       (gauss_row < 4 || gauss_first);
            bypass_q <= gauss_bot[P+16+:8];
            gaussian[P+:8] <= !mode[1] ? bypass_q : gauss_border ? (grayscale ? 8'd0 : bypass_q) : gauss_sum[11:4];

            dx_hi <= weighted(sobel_top[P+16+:8], sobel_mid[P+16+:8], sobel_bot[P+16+:8]);
            dx_lo <= weighted(sobel_top[P+:8], sobel_mid[P+:8], sobel_bot[P+:8]);
            dy_hi <= weighted(sobel_bot[P+:8], sobel_bot[P+8+:8], sobel_bot[P+16+:8]);
            dy_lo <= weighted(sobel_top[P+:8], sobel_top[P+8+:8], sobel_top[P+16+:8]);
            abs_x <= dx_hi >= dx_lo ? dx_hi - dx_lo : dx_lo - dx_hi;
            abs_y <= dy_hi >= dy_lo ? dy_hi - dy_lo : dy_lo - dy_hi;
            edge_pixels[i] <= interior[1] && magnitude >= sobel_threshold;
        end
    end endgenerate

    // The payload is a 1920x1080 raster, LSB-first, then one validity byte.
    // Window anchors are two rows/columns after their center; the viewer aligns them.
    reg [23:0] done_delay, good_delay;
    generate if (EXTENSIONS) begin : advanced_pixels
        reg [2:0] tags_q [0:2];
        always @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                tags_q[0] <= 0;
                tags_q[1] <= 0;
                tags_q[2] <= 0;
            end else begin
                tags_q[0] <= {sobel_window_valid,sobel_window_sof,sobel_window_eol};
                tags_q[1] <= tags_q[0];
                tags_q[2] <= tags_q[1];
            end
        end

        wire [31:0] operated;
        vid007_pixel_ops u_ops (
            .clk(clk), .top(sobel_top), .middle(sobel_mid), .bottom(sobel_bot),
            .interior(sobel_row >= 2 && !sobel_first), .operation(operation),
            .level(level), .pixels(operated)
        );
        wire [31:0] binary_edge = {{8{edge_pixels[3]}},{8{edge_pixels[2]}},
                                   {8{edge_pixels[1]}},{8{edge_pixels[0]}}};
        wire [31:0] advanced_input = mode[2] ? binary_edge : operated;
        wire eq_valid, eq_sof, eq_eol;
        wire [31:0] equalized;
        pp_histeq #(.CW(19)) u_histeq (
            .I_clk(clk), .I_rst_n(rst_n), .I_en(operation == 1 && !mode[2]),
            .I_tdata(advanced_input), .I_tvalid(extended && tags_q[2][2]),
            .I_tuser(tags_q[2][1]), .I_tlast(tags_q[2][0]), .I_tready(),
            .O_tdata(equalized), .O_tvalid(eq_valid), .O_tuser(eq_sof),
            .O_tlast(eq_eol), .O_tready(1'b1), .O_lut_updates()
        );
        wire cl_valid, cl_sof;
        wire [31:0] cl_pixels;
        vid007_clahe clahe (
            .clk(clk),.reset_n(rst_n),.valid(eq_valid),.sof(eq_sof),.eol(eq_eol),
            .pixels(equalized),.enable(operation==7 && !level[7]),.clip({1'b0,level[6:0]}),
            .out_valid(cl_valid),.out_sof(cl_sof),.out_pixels(cl_pixels)
        );
        vid007_subpixel measure (
            .clk(clk),.reset_n(rst_n),.enable(operation==7 && level[7]),
            .valid(eq_valid),.sof(eq_sof),.eol(eq_eol),.done(done_delay[23]),.good(good_delay[23]),
            .pixels(equalized),.threshold({1'b0,level[6:0]}),.result(feature_result)
        );
        assign preview_valid = extended ? cl_valid : gauss_tags[1][2];
        assign preview_sof = extended ? cl_sof : gauss_tags[1][1];
        assign preview_pixels = extended ? cl_pixels : gaussian;
    end else begin : legacy_pixels
        assign feature_result=0;
        assign preview_valid = gauss_tags[1][2];
        assign preview_sof = gauss_tags[1][1];
        assign preview_pixels = gaussian;
    end endgenerate
    assign preview_done = done_delay[23];
    assign preview_good = good_delay[23];
    reg active, half, malformed, trailer, trailer_good;
    reg [3:0] low;
    reg [18:0] bytes_seen;
    wire [2:0] tags = sobel_tags[2];
    wire start = tags[2] && tags[1];
    wire take = tags[2] && (start ? !active && !trailer : active);
    wire byte_ready = take && half && !start;
    assign push = !full && (byte_ready || trailer);
    assign data = byte_ready ? {1'b0, edge_pixels, low} :
                              {1'b1, trailer_good ? {5'b10100, mode} : 8'h00};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            done_delay <= 0;
            good_delay <= 0;
            active <= 0;
            half <= 0;
            low <= 0;
            bytes_seen <= 0;
            malformed <= 0;
            trailer <= 0;
            trailer_good <= 0;
        end else begin
            done_delay <= {done_delay[22:0], frame_done};
            good_delay <= {good_delay[22:0], frame_good};
            if (trailer && !byte_ready && !full)
                trailer <= 0;
            if (start) begin
                if (active) begin
                    active <= 0;
                    trailer <= 1;
                    trailer_good <= 0;
                end else if (!trailer) begin
                    active <= 1;
                    malformed <= 0;
                    bytes_seen <= 0;
                    half <= 1;
                    low <= edge_pixels;
                end
            end else if (take) begin
                half <= !half;
                if (!half)
                    low <= edge_pixels;
                if (byte_ready) begin
                    bytes_seen <= bytes_seen + 1'b1;
                    if (full) malformed <= 1;
                end
                if (tags[0] && !half)
                    malformed <= 1;
            end
            if (done_delay[23] && active) begin
                active <= 0;
                trailer <= 1;
                trailer_good <= good_delay[23] && !malformed && !half &&
                                bytes_seen == 19'd259200;
            end
        end
    end
endmodule
