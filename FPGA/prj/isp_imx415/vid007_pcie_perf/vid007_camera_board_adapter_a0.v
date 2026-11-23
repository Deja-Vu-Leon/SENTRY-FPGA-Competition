// ============================================================
// Module : vid007_camera_board_adapter
// Brief  : VID007 connector reset sequence and open-drain SCL.
// Clocks : I_cfg_clk, nominal 24 MHz from the existing video PLL.
// Reset  : PLL unlock asserts reset asynchronously. Release is
//          synchronized before the sensor reset/settle interval.
// Notes  : Camera INCK comes from the daughtercard oscillator.
// ============================================================
module vid007_camera_board_adapter_a0 #(
    parameter integer CFG_CLK_HZ      = 24000000,
    parameter integer RESET_HOLD_US   = 1000,
    parameter integer RELEASE_WAIT_US = 10000
)(
    input  wire I_cfg_clk,
    input  wire I_pll_locked,
    input  wire I_scl_drive,
    output wire O_scl_od,
    output wire O_xclr_od,
    output wire O_sensor_cfg_rstn
);
    localparam integer RESET_CYCLES = (CFG_CLK_HZ / 1000000) * RESET_HOLD_US;
    localparam integer TOTAL_CYCLES = RESET_CYCLES + (CFG_CLK_HZ / 1000000) * RELEASE_WAIT_US;
    reg        r1_locked;
    reg        r2_locked;
    reg [31:0] r_startup_count;

    // CDC: PLL lock -> configuration clock; asynchronous assertion/synchronous release.
    always @(posedge I_cfg_clk or negedge I_pll_locked) begin
        if (!I_pll_locked) begin
            r1_locked <= 1'b0;
            r2_locked <= 1'b0;
        end else begin
            r1_locked <= 1'b1;
            r2_locked <= r1_locked;
        end
    end

    // Hold XCLR low, release it, then enable the unchanged I2C sequencer.
    always @(posedge I_cfg_clk or negedge I_pll_locked) begin
        if (!I_pll_locked)
            r_startup_count <= 32'd0;
        else if (!r2_locked)
            r_startup_count <= 32'd0;
        else if (r_startup_count < TOTAL_CYCLES)
            r_startup_count <= r_startup_count + 32'd1;
    end

    assign O_sensor_cfg_rstn = r2_locked && (r_startup_count == TOTAL_CYCLES);
    // A0/A1 XCLR: 1.8 V push-pull release.
    assign O_xclr_od         = (r_startup_count < RESET_CYCLES) ? 1'b0 : 1'b1;
    assign O_scl_od          = (O_sensor_cfg_rstn && !I_scl_drive) ? 1'b0 : 1'bz;
endmodule
