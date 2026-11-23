// =============================================================
// Module : dphy_fault_trace
// Brief  : Passive first-skew capture with raw bytes and packet context.
// Clocks : I_sys_clk; all inputs synchronous to this clock.
// Reset  : Asynchronous active-low; capture rearms only on RX reset.
// Notes  : Never feeds the receiver control path. Prehistory is oldest
//          first at output words 16..31; posthistory is words 32..47.
// =============================================================
module dphy_fault_trace (
    input  wire          I_sys_clk,
    input  wire          I_rstn,
    input  wire          I_monitor,
    input  wire          I_skew,
    input  wire [3:0]    I_missing,
    input  wire [3:0]    I_locked,
    input  wire [3:0]    I_sync,
    input  wire [3:0]    I_byte_valid,
    input  wire [11:0]   I_offsets,
    input  wire [19:0]   I_taps,
    input  wire          I_raw_valid,
    input  wire [31:0]   I_raw,
    input  wire          I_pkt_done,
    input  wire [5:0]    I_dt,
    input  wire [15:0]   I_wc,
    input  wire          I_fs,
    input  wire          I_fe,
    input  wire          I_line_good,
    input  wire          I_image_first,
    output wire [1535:0] O_trace
);
    reg  [511:0] r_history;
    reg  [511:0] r_before;
    reg  [511:0] r_after;
    reg  [4:0]   r_post_count;
    reg          r_captured;
    reg          r_next_done;
    reg          r_fe_done;
    reg  [31:0]  r_cycles;
    reg  [31:0]  r_last_done;
    reg  [31:0]  r_last_sync;
    reg  [31:0]  r_events;
    reg  [31:0]  r_frames;
    reg  [15:0]  r_seen;
    reg  [15:0]  r_good;
    reg  [27:0]  r_lane_context;
    reg  [31:0]  r_metadata [1:15];
    integer      r_index;
    wire         S_trigger;

    assign S_trigger = I_monitor && I_skew && !r_captured;

    // Keep continuous prehistory and packet-relative timing before capture.
    always @(posedge I_sys_clk or negedge I_rstn) begin
        if (!I_rstn) begin
            r_history      <= 512'd0;
            r_cycles       <= 32'd0;
            r_last_done    <= 32'd0;
            r_last_sync    <= 32'd0;
            r_events       <= 32'd0;
            r_frames       <= 32'd0;
            r_seen         <= 16'd0;
            r_good         <= 16'd0;
            r_lane_context <= 28'd0;
        end else begin
            if (I_raw_valid) r_history <= {I_raw, r_history[511:32]};
            r_cycles <= r_cycles + 32'd1;
            if (I_pkt_done) r_last_done <= r_cycles;
            if (|I_sync) r_last_sync <= r_cycles;
            if (I_monitor && I_skew) r_events <= r_events + 32'd1;
            r_lane_context <= {I_offsets, I_sync, I_locked, I_byte_valid, 4'd0};
            if (I_fs) begin
                r_frames <= r_frames + 32'd1;
                r_seen   <= 16'd0;
                r_good   <= 16'd0;
            end else begin
                if (I_image_first && !(&r_seen)) r_seen <= r_seen + 16'd1;
                if (I_line_good && !(&r_good)) r_good <= r_good + 16'd1;
            end
        end
    end

    // Freeze the first monitored failure, then collect exactly 16 raw words.
    always @(posedge I_sys_clk or negedge I_rstn) begin
        if (!I_rstn) begin
            r_before     <= 512'd0;
            r_after      <= 512'd0;
            r_post_count <= 5'd0;
            r_captured   <= 1'b0;
            r_next_done  <= 1'b0;
            r_fe_done    <= 1'b0;
            for (r_index = 0; r_index < 15; r_index = r_index + 1)
                r_metadata[r_index+1] <= 32'd0;
        end else begin
            if (S_trigger) begin
                r_captured   <= 1'b1;
                r_before     <= r_history;
                r_metadata[1] <= r_events + 32'd1;
                r_metadata[2] <= r_cycles;
                r_metadata[3] <= r_cycles - r_last_done;
                r_metadata[4] <= {10'd0, I_dt, I_wc};
                r_metadata[5] <= {4'd0, r_lane_context[27:4], I_missing};
                r_metadata[6] <= {r_seen, r_good};
                r_metadata[7] <= r_frames;
                r_metadata[10] <= r_cycles - r_last_sync;
                r_metadata[11] <= {12'd0, I_taps};
                r_metadata[15] <= {27'd0, I_pkt_done, I_fs, I_fe, I_raw_valid, I_monitor};
            end
            if ((S_trigger || r_captured) && (r_post_count < 5'd16) && I_raw_valid) begin
                r_after[r_post_count*32+:32] <= I_raw;
                r_post_count <= r_post_count + 5'd1;
            end
            if (r_captured && I_pkt_done && !r_next_done) begin
                r_next_done <= 1'b1;
                r_metadata[8] <= r_cycles - r_metadata[2];
                r_metadata[9] <= {10'd0, I_dt, I_wc};
            end
            if (r_captured && I_fe && !r_fe_done) begin
                r_fe_done <= 1'b1;
                r_metadata[12] <= {r_seen, r_good};
                r_metadata[13] <= r_cycles - r_metadata[2];
                r_metadata[14] <= r_frames;
            end
        end
    end

    assign O_trace[0+:32] = {24'h545236, 4'd0, r_fe_done, r_next_done,
                             (r_post_count == 5'd16), r_captured};
    genvar g_word;
    generate
        for (g_word = 1; g_word < 16; g_word = g_word + 1) begin : g_metadata
            assign O_trace[g_word*32+:32] = r_metadata[g_word];
        end
    endgenerate
    assign O_trace[512+:512]  = r_before;
    assign O_trace[1024+:512] = r_after;
endmodule
