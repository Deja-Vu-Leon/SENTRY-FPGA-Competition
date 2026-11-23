// ============================================================
// Module : vid008_rx_isp_adapter
// Brief  : Connect the MIPI receiver output to the ISP input.
// Clocks : I_rx_clk = 150 MHz; I_cfg_done crosses from sensor config.
// Reset  : Asynchronous assertion, synchronized release in RX domain.
// Notes  : M2 words 0..12 retain the public RX IP debug ABI exactly.
//          Frame buffering is provided by the downstream DDR subsystem.
// ============================================================
module vid008_rx_isp_adapter (
    input  wire         I_rx_clk,
    input  wire         I_rstn,
    input  wire         I_cfg_done,
    input  wire         I_cam_clk_p,
    input  wire [3:0]   I_cam_d_p,

    output wire         O_frame_done,
    output wire         O_frame_good,
    output wire         O_valid,
    output wire [39:0]  O_data,
    output wire         O_sof,
    output wire         O_eol,
    output wire [767:0] O_health,
    output wire [1535:0] O_fault_trace
);
    wire         S_rstn;
    reg          r1_cfg_done;
    reg          r2_cfg_done;
    wire         S_valid;
    wire [31:0]  S_data;
    wire [2:0]   S_bytes;
    wire         S_first;
    wire         S_last;
    wire         S_frame_start;
    wire         S_frame_done;
    wire         S_frame_good;
    wire         S_ready;
    wire         S_error;
    wire         S_format_error;
    wire [415:0] S_debug;
    reg  [31:0]  r_starts;
    reg  [31:0]  r_good;
    reg  [31:0]  r_bad;
    reg  [31:0]  r_format_errors;
    reg  [31:0]  r_axis_frames;
    reg  [31:0]  r_axis_lines;
    reg  [31:0]  r_axis_beats;
    reg  [31:0]  r_frame_lines;
    reg  [31:0]  r_frame_beats;
    reg  [31:0]  r_previous_lines;
    reg  [31:0]  r_previous_beats;
    reg  [31:0]  r_ready_losses;
    reg          r_ready;

    dphy_rst_sync #(.STAGES(3)) u_reset (
        .I_clk  (I_rx_clk),
        .I_rstn (I_rstn),
        .O_rstn (S_rstn)
    );

    // CDC: sensor configuration clock -> RX system clock.
    always @(posedge I_rx_clk or negedge S_rstn) begin
        if (!S_rstn) begin
            r1_cfg_done <= 1'b0;
            r2_cfg_done <= 1'b0;
        end else begin
            r1_cfg_done <= I_cfg_done;
            r2_cfg_done <= r1_cfg_done;
        end
    end

    mipi_rx_ip_top u_rx (
        .I_sys_clk       (I_rx_clk),
        .I_rstn          (S_rstn),
        .I_enable        (r2_cfg_done),
        .I_cam_clk_p     (I_cam_clk_p),
        .I_cam_d_p       (I_cam_d_p),
        .O_data_valid    (S_valid),
        .O_data          (S_data),
        .O_data_bytes    (S_bytes),
        .O_data_first    (S_first),
        .O_data_last     (S_last),
        .O_line_good     (),
        .O_frame_start   (S_frame_start),
        .O_frame_done    (S_frame_done),
        .O_frame_good    (S_frame_good),
        .O_frame_timeout (),
        .O_ready         (S_ready),
        .O_error_sticky  (S_error),
        .O_lane_taps     (),
        .O_lane_margin   (),
        .O_train_state   (),
        .O_lane_fail     (),
        .O_retrain_count (),
        .O_line_bad      (),
        .O_frame_error   (),
        .O_debug_status  (S_debug),
        .O_fault_trace   (O_fault_trace)
    );


    assign O_frame_done = S_frame_done;
    assign O_frame_good = S_frame_good;

    mipi_raw10_crop u_crop (
        .I_rx_clk       (I_rx_clk),
        .I_rstn         (S_rstn),
        .I_ready        (S_ready),
        .I_frame_start  (S_frame_start),
        .I_frame_done   (S_frame_done),
        .I_valid        (S_valid),
        .I_data         (S_data),
        .I_bytes        (S_bytes),
        .I_first        (S_first),
        .I_last         (S_last),
        .O_valid        (O_valid),
        .O_data         (O_data),
        .O_sof          (O_sof),
        .O_eol          (O_eol),
        .O_format_error (S_format_error)
    );

    // Count guard results separately from provisional ISP input traffic.
    always @(posedge I_rx_clk or negedge S_rstn) begin
        if (!S_rstn) begin
            r_starts         <= 32'd0;
            r_good           <= 32'd0;
            r_bad            <= 32'd0;
            r_format_errors  <= 32'd0;
            r_axis_frames    <= 32'd0;
            r_axis_lines     <= 32'd0;
            r_axis_beats     <= 32'd0;
            r_frame_lines    <= 32'd0;
            r_frame_beats    <= 32'd0;
            r_previous_lines <= 32'd0;
            r_previous_beats <= 32'd0;
            r_ready_losses   <= 32'd0;
            r_ready          <= 1'b0;
        end else begin
            r_ready <= S_ready;
            if (r_ready && !S_ready) r_ready_losses <= r_ready_losses + 32'd1;
            if (S_format_error) r_format_errors <= r_format_errors + 32'd1;
            if (S_frame_start) begin
                r_starts      <= r_starts + 32'd1;
                r_frame_lines <= 32'd0;
                r_frame_beats <= 32'd0;
            end
            if (S_frame_done) begin
                if (S_frame_good) r_good <= r_good + 32'd1;
                else r_bad <= r_bad + 32'd1;
                r_previous_lines <= r_frame_lines;
                r_previous_beats <= r_frame_beats;
            end
            if (O_valid) begin
                r_axis_beats  <= r_axis_beats + 32'd1;
                r_frame_beats <= r_frame_beats + 32'd1;
                if (O_sof) r_axis_frames <= r_axis_frames + 32'd1;
                if (O_eol) begin
                    r_axis_lines  <= r_axis_lines + 32'd1;
                    r_frame_lines <= r_frame_lines + 32'd1;
                end
            end
        end
    end

    assign O_health[0*32+:416] = S_debug;
    assign O_health[13*32+:32] = r_starts;
    assign O_health[14*32+:32] = r_good;
    assign O_health[15*32+:32] = r_bad;
    assign O_health[16*32+:32] = r_format_errors;
    assign O_health[17*32+:32] = r_axis_frames;
    assign O_health[18*32+:32] = r_axis_lines;
    assign O_health[19*32+:32] = r_axis_beats;
    assign O_health[20*32+:32] = r_previous_lines;
    assign O_health[21*32+:32] = r_previous_beats;
    assign O_health[22*32+:32] = r_ready_losses;
    assign O_health[23*32+:32] = {30'd0, S_error, S_ready};
endmodule
