// ============================================================
// Module : mipi_raw10_crop
// Brief  : Unpack counted CSI-2 RAW10 bytes and select an aligned ROI.
// Clocks : I_rx_clk, synchronous with the accepted receiver output.
// Reset  : I_rstn asynchronous low; caller synchronizes release.
// Notes  : No backpressure. Pixels remain provisional until frame_good.
//          Coordinates count RAW lines only, excluding embedded packets.
// ============================================================
module mipi_raw10_crop #(
    parameter integer IMAGE_WIDTH  = 1944,
    parameter integer IMAGE_HEIGHT = 1097,
    parameter integer CROP_X       = 4,
    parameter integer CROP_Y       = 16,
    parameter integer CROP_WIDTH   = 1920,
    parameter integer CROP_HEIGHT  = 1080
) (
    input  wire        I_rx_clk,
    input  wire        I_rstn,
    input  wire        I_ready,
    input  wire        I_frame_start,
    input  wire        I_frame_done,
    input  wire        I_valid,
    input  wire [31:0] I_data,
    input  wire [2:0]  I_bytes,
    input  wire        I_first,
    input  wire        I_last,
    output reg         O_valid,
    output reg  [39:0] O_data,
    output reg         O_sof,
    output reg         O_eol,
    output reg         O_format_error
);
    localparam [15:0] IMAGE_BYTES = IMAGE_WIDTH / 4 * 5;
    localparam [15:0] FIRST_GROUP = CROP_X / 4;
    localparam [15:0] END_GROUP   = (CROP_X + CROP_WIDTH) / 4;
    localparam [15:0] FIRST_LINE  = CROP_Y;
    localparam [15:0] END_LINE    = CROP_Y + CROP_HEIGHT;

    reg         r_frame_active;
    reg         r_line_open;
    reg  [31:0] r_carry;
    reg  [2:0]  r_count;
    reg  [15:0] r_line_bytes;
    reg  [15:0] r_line;
    reg  [15:0] r_group;
    wire [2:0]  S_count      = I_first ? 3'd0 : r_count;
    wire [31:0] S_carry      = I_first ? 32'd0 : r_carry;
    wire [15:0] S_group      = I_first ? 16'd0 : r_group;
    wire [15:0] S_line_bytes = I_first ? 16'd0 : r_line_bytes;
    wire [3:0]  S_total      = {1'b0, S_count} + {1'b0, I_bytes};
    wire [15:0] S_byte_total = S_line_bytes + {13'd0, I_bytes};
    wire [31:0] S_mask       = 32'hFFFFFFFF >> ((3'd4 - I_bytes) * 8);
    wire [63:0] S_joined     = {32'd0, S_carry} | ({32'd0, I_data & S_mask} << (S_count * 8));
    wire        S_emit       = S_total >= 4'd5;
    wire        S_inside     = (r_line >= FIRST_LINE) && (r_line < END_LINE) &&
                               (S_group >= FIRST_GROUP) && (S_group < END_GROUP);
    wire        S_bad_bytes  = (I_bytes == 3'd0) || (I_bytes > 3'd4);
    wire        S_bad_end    = I_last && ((S_byte_total != IMAGE_BYTES) || (S_total != 4'd5));
    wire        S_bad_start  = I_first ? r_line_open : !r_line_open;

    generate
        if ((IMAGE_WIDTH % 4 != 0) || (CROP_X % 4 != 0) || (CROP_WIDTH % 4 != 0) ||
            (CROP_X + CROP_WIDTH > IMAGE_WIDTH) || (CROP_Y + CROP_HEIGHT > IMAGE_HEIGHT) ||
            (CROP_WIDTH < 4) || (CROP_HEIGHT < 1)) begin : g_invalid_geometry
            RAW10_CROP_REQUIRES_VALID_QUAD_ALIGNED_GEOMETRY u_parameter_error ();
        end
    endgenerate

    // Bytes are consumed only once; bubbles never repeat the previous output.
    always @(posedge I_rx_clk or negedge I_rstn) begin
        if (!I_rstn) begin
            r_frame_active <= 1'b0;
            r_line_open    <= 1'b0;
            r_carry        <= 32'd0;
            r_count        <= 3'd0;
            r_line_bytes   <= 16'd0;
            r_line         <= 16'd0;
            r_group        <= 16'd0;
            O_valid        <= 1'b0;
            O_data         <= 40'd0;
            O_sof          <= 1'b0;
            O_eol          <= 1'b0;
            O_format_error <= 1'b0;
        end else begin
            O_valid        <= 1'b0;
            O_sof          <= 1'b0;
            O_eol          <= 1'b0;
            O_format_error <= 1'b0;
            if (!I_ready || I_frame_start || I_frame_done) begin
                r_frame_active <= I_ready && I_frame_start;
                r_line_open    <= 1'b0;
                r_carry        <= 32'd0;
                r_count        <= 3'd0;
                r_line_bytes   <= 16'd0;
                r_line         <= 16'd0;
                r_group        <= 16'd0;
            end else if (I_valid && r_frame_active) begin
                O_format_error <= S_bad_bytes || S_bad_start || S_bad_end || (r_line >= IMAGE_HEIGHT);
                r_line_open    <= !I_last;
                r_line_bytes   <= S_byte_total;
                if (S_emit) begin
                    O_valid <= S_inside && !S_bad_bytes && !S_bad_start;
                    O_data  <= {S_joined[31:24], S_joined[39:38],
                                S_joined[23:16], S_joined[37:36],
                                S_joined[15:8],  S_joined[35:34],
                                S_joined[7:0],   S_joined[33:32]};
                    O_sof   <= S_inside && (r_line == FIRST_LINE) && (S_group == FIRST_GROUP);
                    O_eol   <= S_inside && (S_group == END_GROUP - 16'd1);
                    r_carry <= {8'd0, S_joined[63:40]};
                    r_count <= S_total - 4'd5;
                    r_group <= S_group + 16'd1;
                end else begin
                    r_carry <= S_joined[31:0];
                    r_count <= S_total[2:0];
                    r_group <= S_group;
                end
                if (I_last) begin
                    r_line  <= r_line + 16'd1;
                    r_carry <= 32'd0;
                    r_count <= 3'd0;
                    r_group <= 16'd0;
                end
            end
        end
    end
endmodule
