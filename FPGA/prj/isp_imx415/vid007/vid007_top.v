`timescale 1ns/1ps


module vid007_top #(
    parameter LINK_WIDTH    = 1,
    parameter DEVICE_FAMILY = "PH1A",
    parameter USER_CLK_FREQ = 125,
    parameter DATA_WIDTH    = 128,
    parameter KEEP_WIDTH    = DATA_WIDTH/8,
    parameter H2C_CHNL_NUM  = 1,
    parameter C2H_CHNL_NUM  = 1,
    parameter USR_IRQ_NUM   = 16
)(
    // ���� System ����
    input   wire                    sys_clk,        // 25 MHz

    // ���� PCIe ����
    input   wire                    refclk_p,
    input   wire                    refclk_n,
    output  wire   [LINK_WIDTH-1:0] txp,
    output  wire   [LINK_WIDTH-1:0] txn,
    input   wire   [LINK_WIDTH-1:0] rxp,
    input   wire   [LINK_WIDTH-1:0] rxn,
    input   wire                    pcie_mperst,

    // ���� MIPI Reference Clock (100MHz LVDS differential, T13/T14) ����
    input   wire                    mipi_ref_clk_p,         // 100MHz LVDS P (T13)
    input wire a0_clk,
    input wire [3:0] a0_data,
    output wire a0_scl, a0_reset,
    inout wire a0_sda,
    input wire a1_clk,
    input wire [3:0] a1_data,
    output wire a1_scl, a1_reset,
    inout wire a1_sda,
    input wire b0_clk,
    input wire [3:0] b0_data,
    output wire b0_scl, b0_reset,
    inout wire b0_sda,
    input wire b1_clk,
    input wire [3:0] b1_data,
    output wire b1_scl, b1_reset,
    inout wire b1_sda
);
// Compile-time feature enable (same as Phase 8)
// ====================================================================
`ifdef  MSI_EN
localparam IRQ_LGCY_EN = 0; localparam IRQ_MSI_EN = 1; localparam IRQ_MSIX_EN = 0;
`elsif   MSIX_EN
localparam IRQ_LGCY_EN = 0; localparam IRQ_MSI_EN = 0; localparam IRQ_MSIX_EN = 1;
`else
localparam IRQ_LGCY_EN = 1; localparam IRQ_MSI_EN = 0; localparam IRQ_MSIX_EN = 0;
`endif
`ifdef  AXI4MM_BUS_EN          localparam AXI4MM_BUS_EN    = 1; `else localparam AXI4MM_BUS_EN    = 0; `endif
`ifdef  AXI4ST_BUS_EN          localparam AXI4ST_BUS_EN    = 1; `else localparam AXI4ST_BUS_EN    = 0; `endif
`ifdef  DSC_BYPASS_C2H_CHL0_EN localparam DSC_BYPASS_C2H0  = 1; `else localparam DSC_BYPASS_C2H0  = 0; `endif
`ifdef  DSC_BYPASS_C2H_CHL1_EN localparam DSC_BYPASS_C2H1  = 2; `else localparam DSC_BYPASS_C2H1  = 0; `endif
`ifdef  DSC_BYPASS_C2H_CHL2_EN localparam DSC_BYPASS_C2H2  = 4; `else localparam DSC_BYPASS_C2H2  = 0; `endif
`ifdef  DSC_BYPASS_C2H_CHL3_EN localparam DSC_BYPASS_C2H3  = 8; `else localparam DSC_BYPASS_C2H3  = 0; `endif
`ifdef  DSC_BYPASS_H2C_CHL0_EN localparam DSC_BYPASS_H2C0  = 1; `else localparam DSC_BYPASS_H2C0  = 0; `endif
`ifdef  DSC_BYPASS_H2C_CHL1_EN localparam DSC_BYPASS_H2C1  = 2; `else localparam DSC_BYPASS_H2C1  = 0; `endif
`ifdef  DSC_BYPASS_H2C_CHL2_EN localparam DSC_BYPASS_H2C2  = 4; `else localparam DSC_BYPASS_H2C2  = 0; `endif
`ifdef  DSC_BYPASS_H2C_CHL3_EN localparam DSC_BYPASS_H2C3  = 8; `else localparam DSC_BYPASS_H2C3  = 0; `endif
localparam [3:0]    H2C_DSC_BYP_MAP = DSC_BYPASS_H2C0 | DSC_BYPASS_H2C1 | DSC_BYPASS_H2C2 | DSC_BYPASS_H2C3;
localparam [3:0]    C2H_DSC_BYP_MAP = DSC_BYPASS_C2H0 | DSC_BYPASS_C2H1 | DSC_BYPASS_C2H2 | DSC_BYPASS_C2H3;
localparam          DESC_BYP_EN     = (C2H_DSC_BYP_MAP || H2C_DSC_BYP_MAP) ? 1'b1 : 1'b0;

// ====================================================================
// Internal wires
// ====================================================================

`ifdef AXI4ST_BUS_EN
    wire    [C2H_CHNL_NUM-1:0]             s0_axis_c2h_tready;
    wire    [DATA_WIDTH*C2H_CHNL_NUM-1:0]  s0_axis_c2h_tdata;
    wire    [KEEP_WIDTH*C2H_CHNL_NUM-1:0]  s0_axis_c2h_tkeep;
    wire    [KEEP_WIDTH*C2H_CHNL_NUM-1:0]  s0_axis_c2h_tuser;
    wire    [C2H_CHNL_NUM-1:0]             s0_axis_c2h_tlast;
    wire    [C2H_CHNL_NUM-1:0]             s0_axis_c2h_tvalid;

    wire    [H2C_CHNL_NUM-1:0]             m0_axis_h2c_tready;
    wire    [DATA_WIDTH*H2C_CHNL_NUM-1:0]  m0_axis_h2c_tdata;
    wire    [KEEP_WIDTH*H2C_CHNL_NUM-1:0]  m0_axis_h2c_tkeep;
    wire    [KEEP_WIDTH*H2C_CHNL_NUM-1:0]  m0_axis_h2c_tuser;
    wire    [H2C_CHNL_NUM-1:0]             m0_axis_h2c_tlast;
    wire    [H2C_CHNL_NUM-1:0]             m0_axis_h2c_tvalid;

    wire    [C2H_CHNL_NUM-1:0]             app_c2h_tready;
    wire    [DATA_WIDTH*C2H_CHNL_NUM-1:0]  app_c2h_tdata;
    wire    [KEEP_WIDTH*C2H_CHNL_NUM-1:0]  app_c2h_tkeep;
    wire    [KEEP_WIDTH*C2H_CHNL_NUM-1:0]  app_c2h_tuser;
    wire    [C2H_CHNL_NUM-1:0]             app_c2h_tlast;
    wire    [C2H_CHNL_NUM-1:0]             app_c2h_tvalid;

    // Camera output (128-bit AXI-Stream)
    wire    [DATA_WIDTH-1:0]                cam_tdata;
    wire                                    cam_tvalid;
    wire                                    cam_tready;
    wire                                    cam_tlast;
    wire                                    cam_frame_last;
    wire                                    cam_sof;
    wire                                    cam_eof;
`endif

`ifdef AXI4L_MBUS_EN
    wire    [31:0]                          m_axil_awaddr;
    wire    [2:0]                           m_axil_awprot;
    wire                                    m_axil_awvalid;
    wire                                    m_axil_awready;
    wire    [31:0]                          m_axil_wdata;
    wire    [3:0]                           m_axil_wstrb;
    wire                                    m_axil_wvalid;
    wire                                    m_axil_wready;
    wire                                    m_axil_bvalid;
    wire    [1:0]                           m_axil_bresp;
    wire                                    m_axil_bready;
    wire    [31:0]                          m_axil_araddr;
    wire    [2:0]                           m_axil_arprot;
    wire                                    m_axil_arvalid;
    wire                                    m_axil_arready;
    wire    [31:0]                          m_axil_rdata;
    wire    [1:0]                           m_axil_rresp;
    wire                                    m_axil_rvalid;
    wire                                    m_axil_rready;
    wire    [31:0]                          app_axil_rdata;
`ifndef AXI4ST_BUS_EN
    assign m_axil_rdata = app_axil_rdata;
`endif
`endif

`ifdef USR_IRQ_EN
    wire    [USR_IRQ_NUM-1:0]               usr_irq_req;
    wire    [USR_IRQ_NUM-1:0]               usr_irq_ack;
    wire                                    msi_enable;
    wire    [4:0]                           msi_vector_width;
`endif

`ifdef DSC_BYPASS_C2H_CHL0_EN
    wire c2h_dsc_byp_ready_0, c2h_dsc_byp_load_0;
    wire [63:0] c2h_dsc_byp_src_addr_0, c2h_dsc_byp_dst_addr_0;
    wire [27:0] c2h_dsc_byp_len_0;
    wire [15:0] c2h_dsc_byp_ctl_0;
`endif
`ifdef DSC_BYPASS_H2C_CHL0_EN
    wire h2c_dsc_byp_ready_0, h2c_dsc_byp_load_0;
    wire [63:0] h2c_dsc_byp_src_addr_0, h2c_dsc_byp_dst_addr_0;
    wire [27:0] h2c_dsc_byp_len_0;
    wire [15:0] h2c_dsc_byp_ctl_0;
`endif

    wire [7:0] c2h_sts_0, h2c_sts_0, c2h_sts_1, h2c_sts_1;
    wire [7:0] c2h_sts_2, h2c_sts_2, c2h_sts_3, h2c_sts_3;

    wire        sys_clk_g;
    wire        app_auxclk;
    wire        user_clk;
    wire        user_rst_n;
    wire        core_clk;
    wire        pll_lock;
    wire        user_link_up;

// ====================================================================
// Internal Power-On Reset
// ====================================================================
    reg  [9:0]  int_por_cnt = 10'd0;
    wire        int_por_done = &int_por_cnt;
    reg         int_por_done_r = 1'b0;

    always @(posedge sys_clk_g) begin
        if (!int_por_done)
            int_por_cnt <= int_por_cnt + 1'b1;
        int_por_done_r <= int_por_done;
    end

// ====================================================================
// Global Clock Buffer
// ====================================================================
PH1_LOGIC_BUFG u_sys_clk_bufg (
    .i  (sys_clk    ),
    .o  (sys_clk_g  )
);

// ====================================================================
// MIPI Reference Clock: 100MHz LVDS differential input (T13/T14)
// TD auto-infers LVDS input buffer from IOSTANDARD=LVDS18 constraint.
// Route through BUFG for global clock tree.
// ====================================================================
    wire mipi_ref_clk_bufg;
PH1_LOGIC_BUFG u_mipi_ref_clk_bufg (
    .i  (mipi_ref_clk_p ),
    .o  (mipi_ref_clk_bufg)
);

// ====================================================================
// Camera PLL: 100MHz LVDS -> 150MHz (cam_pclk) + 100MHz (cam_100m) + 24MHz (cam_24m)
// cam_pclk  = mipi_ref_clock for MIPI PHY (150MHz required for Eye-Scan)
// cam_100m  = reserved
// cam_24m   = MCLK source (ODDR) + I2C master clock
// ====================================================================
    wire cam_pclk, cam_100m, cam_24m, ui_pll_lock;
ui_pll u_ui_pll (
    .refclk     (mipi_ref_clk_bufg  ),
    .reset      (1'b0              ),
    .lock       (ui_pll_lock        ),
    .clk0_out   (cam_pclk           ),
    .clk1_out   (cam_100m           ),
    .clk2_out   (cam_24m            )
);

// ====================================================================
// PLL: 25MHz -> 125MHz (core_clk) + 25MHz (app_auxclk)
// ====================================================================
sgdma_pll u_sgdma_pll(
    .refclk     (sys_clk_g          ),
    .reset      (!int_por_done_r    ),
    .lock       (pll_lock           ),
    .clk0_out   (core_clk           ),
    .clk1_out   (app_auxclk         )
);

// ====================================================================
// PERST# + PLL stable
// ====================================================================
    reg  [21:0] pll_lock_cnt;
    wire        pll_lock_stable_comb = (pll_lock_cnt == 22'h3FFFFF);

    always @(posedge core_clk or negedge pll_lock) begin
        if (!pll_lock)
            pll_lock_cnt <= 22'd0;
        else if (!pll_lock_stable_comb)
            pll_lock_cnt <= pll_lock_cnt + 1'b1;
    end

    reg pll_lock_stable;
    always @(posedge core_clk or negedge pll_lock) begin
        if (!pll_lock)
            pll_lock_stable <= 1'b0;
        else
            pll_lock_stable <= pll_lock_stable_comb;
    end

    wire tl_power_on_rstn = pcie_mperst & pll_lock_stable;

sgdma_subsys #(
    .USER_CLK_FREQ  (USER_CLK_FREQ),
    .DEVICE_FAMILY  (DEVICE_FAMILY),
    .LINK_WIDTH     (LINK_WIDTH),
    .DATA_WIDTH     (DATA_WIDTH),
    .H2C_CHNL_NUM  (H2C_CHNL_NUM),
    .C2H_CHNL_NUM  (C2H_CHNL_NUM),
    // v0629 tried .H2C_ID_NUM(8) (default 32, ~11 ERAM less): stream 1's mux FIFO then peaked at 8155 / 8192 within 3 min on the board
    // (5776 in a day on v0628) - fewer read tags slow the C2H path; reverted in v0630, the ERAM is not needed (TTT +10 of 63 free)
    .USR_IRQ_NUM    (USR_IRQ_NUM),
    .LGCY_EN        (IRQ_LGCY_EN),
    .MSI_EN         (IRQ_MSI_EN),
    .MSIX_EN        (IRQ_MSIX_EN),
    .AXI4MM_BUS_EN  (AXI4MM_BUS_EN),
    .AXI4ST_BUS_EN  (AXI4ST_BUS_EN),
    .H2C_DSC_BYP_MAP(H2C_DSC_BYP_MAP),
    .C2H_DSC_BYP_MAP(C2H_DSC_BYP_MAP)
) u_sgdma_subsys(
    .app_auxclk             (app_auxclk),
    .tl_power_on_rstn       (tl_power_on_rstn),
    .tl_clk_user            (core_clk),
    .pll_lock               (pll_lock),
    .ref_pad_clk_p          (refclk_p),
    .ref_pad_clk_n          (refclk_n),
    .pcie_tx_p              (txp),
    .pcie_tx_n              (txn),
    .pcie_rx_p              (rxp),
    .pcie_rx_n              (rxn),
    .c2h_sts_0              (c2h_sts_0),
    .h2c_sts_0              (h2c_sts_0),
    .c2h_sts_1              (c2h_sts_1),
    .h2c_sts_1              (h2c_sts_1),
    .c2h_sts_2              (c2h_sts_2),
    .h2c_sts_2              (h2c_sts_2),
    .c2h_sts_3              (c2h_sts_3),
    .h2c_sts_3              (h2c_sts_3),
`ifdef AXI4ST_BUS_EN
    .s0_axis_c2h_tready     (s0_axis_c2h_tready),
    .s0_axis_c2h_tdata      (s0_axis_c2h_tdata),
    .s0_axis_c2h_tkeep      (s0_axis_c2h_tkeep),
    .s0_axis_c2h_tuser      (s0_axis_c2h_tuser),
    .s0_axis_c2h_tlast      (s0_axis_c2h_tlast),
    .s0_axis_c2h_tvalid     (s0_axis_c2h_tvalid),
    .m0_axis_h2c_tready     (m0_axis_h2c_tready),
    .m0_axis_h2c_tdata      (m0_axis_h2c_tdata),
    .m0_axis_h2c_tkeep      (m0_axis_h2c_tkeep),
    .m0_axis_h2c_tuser      (m0_axis_h2c_tuser),
    .m0_axis_h2c_tlast      (m0_axis_h2c_tlast),
    .m0_axis_h2c_tvalid     (m0_axis_h2c_tvalid),
`endif
`ifdef AXI4L_MBUS_EN
    .m_axil_awaddr          (m_axil_awaddr),
    .m_axil_awprot          (m_axil_awprot),
    .m_axil_awvalid         (m_axil_awvalid),
    .m_axil_awready         (m_axil_awready),
    .m_axil_wdata           (m_axil_wdata),
    .m_axil_wstrb           (m_axil_wstrb),
    .m_axil_wvalid          (m_axil_wvalid),
    .m_axil_wready          (m_axil_wready),
    .m_axil_bvalid          (m_axil_bvalid),
    .m_axil_bresp           (m_axil_bresp),
    .m_axil_bready          (m_axil_bready),
    .m_axil_araddr          (m_axil_araddr),
    .m_axil_arprot          (m_axil_arprot),
    .m_axil_arvalid         (m_axil_arvalid),
    .m_axil_arready         (m_axil_arready),
    .m_axil_rdata           (m_axil_rdata),
    .m_axil_rresp           (m_axil_rresp),
    .m_axil_rvalid          (m_axil_rvalid),
    .m_axil_rready          (m_axil_rready),
`endif
`ifdef DSC_BYPASS_C2H_CHL0_EN
    .c2h_dsc_byp_ready_0_o (c2h_dsc_byp_ready_0),
    .c2h_dsc_byp_load_0_i  (c2h_dsc_byp_load_0),
    .c2h_dsc_byp_src_addr_0_i(c2h_dsc_byp_src_addr_0),
    .c2h_dsc_byp_dst_addr_0_i(c2h_dsc_byp_dst_addr_0),
    .c2h_dsc_byp_len_0_i   (c2h_dsc_byp_len_0),
    .c2h_dsc_byp_ctl_0_i   (c2h_dsc_byp_ctl_0),
`endif
`ifdef DSC_BYPASS_H2C_CHL0_EN
    .h2c_dsc_byp_ready_0_o (h2c_dsc_byp_ready_0),
    .h2c_dsc_byp_load_0_i  (h2c_dsc_byp_load_0),
    .h2c_dsc_byp_src_addr_0_i(h2c_dsc_byp_src_addr_0),
    .h2c_dsc_byp_dst_addr_0_i(h2c_dsc_byp_dst_addr_0),
    .h2c_dsc_byp_len_0_i   (h2c_dsc_byp_len_0),
    .h2c_dsc_byp_ctl_0_i   (h2c_dsc_byp_ctl_0),
`endif
`ifdef USR_IRQ_EN
    .usr_irq_req            (usr_irq_req),
    .usr_irq_ack            (usr_irq_ack),
    .msi_enable             (msi_enable),
    .msi_vector_width       (msi_vector_width),
`endif
    .user_link_up           (user_link_up),
    .user_clk               (user_clk),
    .user_rst_n             (user_rst_n)
);


    reg capture_enable;
    reg version_read;
    always @(posedge user_clk or negedge user_rst_n) begin
        if (!user_rst_n) begin
            capture_enable <= 0;
            version_read <= 0;
        end else begin
            if (m_axil_awvalid && m_axil_wvalid && m_axil_awready && m_axil_wready &&
                m_axil_awaddr[15:0] == 16'h0060 && m_axil_wstrb[0])
                capture_enable <= m_axil_wdata[0] && !m_axil_wdata[1];
            version_read <= m_axil_arvalid && m_axil_araddr[15:0] == 16'h0040;
        end
    end
    assign m_axil_rdata = version_read ? 32'h56070401 : app_axil_rdata;

    wire stream_rst_n = user_rst_n && user_link_up && capture_enable;
    wire rx_stream_rst_n;
    dphy_rst_sync #(.STAGES(3)) u_stream_reset (
        .I_clk(cam_pclk), .I_rstn(stream_rst_n && ui_pll_lock), .O_rstn(rx_stream_rst_n)
    );
    wire [8:0] stream_data [0:3];
    wire [3:0] stream_valid, room;
    assign app_c2h_tready = 0;

    pcie_jpg_mux4 #(.MAX_CHUNK(4080), .FIFO_AW0(13), .FIFO_AW1(13),
                    .FIFO_AW2(13), .FIFO_AW3(13)) u_mux (
        .clk(user_clk), .rst_n(stream_rst_n), .I_hwm_clr(1'b0),
        .I_s0_tdata(stream_data[0][7:0]), .I_s0_tvalid(stream_valid[0]),
        .I_s0_tlast(stream_valid[0] && stream_data[0][8]), .O_s0_room(room[0]),
        .I_s1_tdata(stream_data[1][7:0]), .I_s1_tvalid(stream_valid[1]),
        .I_s1_tlast(stream_valid[1] && stream_data[1][8]), .O_s1_room(room[1]),
        .I_s2_tdata(stream_data[2][7:0]), .I_s2_tvalid(stream_valid[2]),
        .I_s2_tlast(stream_valid[2] && stream_data[2][8]), .O_s2_room(room[2]),
        .I_s3_tdata(stream_data[3][7:0]), .I_s3_tvalid(stream_valid[3]),
        .I_s3_tlast(stream_valid[3] && stream_data[3][8]), .O_s3_room(room[3]),
        .m_tdata(s0_axis_c2h_tdata), .m_tkeep(s0_axis_c2h_tkeep),
        .m_tuser(s0_axis_c2h_tuser), .m_tvalid(s0_axis_c2h_tvalid),
        .m_tready(s0_axis_c2h_tready), .m_tlast(s0_axis_c2h_tlast)
    );

    wire a0_cfg_rst_n, a0_scl_drive, a0_configured;
    vid007_camera_board_adapter_a0 u_a0_board (
        .I_cfg_clk(cam_24m), .I_pll_locked(ui_pll_lock),
        .I_scl_drive(a0_scl_drive), .O_scl_od(a0_scl),
        .O_xclr_od(a0_reset), .O_sensor_cfg_rstn(a0_cfg_rst_n)
    );
    ui_cfg_imx415 #(.CLK_DIV(239)) u_a0_cfg (
        .I_clk(cam_24m), .I_rst_n(a0_cfg_rst_n), .I_ae_req(1'b0), .I_ae_data(0),
        .O_cam_scl(a0_scl_drive), .IO_cam_sda(a0_sda), .O_cfg_done(a0_configured)
    );
    wire [39:0] a0_raw;
    wire a0_valid, a0_sof, a0_eol, a0_done, a0_good;
    vid008_rx_isp_adapter u_a0_rx (
        .I_rx_clk(cam_pclk), .I_rstn(ui_pll_lock), .I_cfg_done(a0_configured),
        .I_cam_clk_p(a0_clk), .I_cam_d_p(a0_data),
        .O_valid(a0_valid), .O_data(a0_raw), .O_sof(a0_sof), .O_eol(a0_eol),
        .O_frame_done(a0_done), .O_frame_good(a0_good)
    );
    wire [8:0] a0_fifo_in;
    wire a0_push, a0_full, a0_empty;
    vid007_gray u_a0_gray (
        .clk(cam_pclk), .rst_n(rx_stream_rst_n), .valid(a0_valid),
        .sof(a0_sof), .eol(a0_eol), .raw10(a0_raw),
        .frame_done(a0_done), .frame_good(a0_good),
        .full(a0_full), .push(a0_push), .data(a0_fifo_in)
    );
    dphy_raw_async_fifo #(.WIDTH(9), .AW(10)) u_a0_fifo (
        .I_wr_clk(cam_pclk), .I_wr_rstn(rx_stream_rst_n), .I_wr_en(a0_push),
        .I_wr_data(a0_fifo_in), .O_wr_full(a0_full),
        .I_rd_clk(user_clk), .I_rd_rstn(stream_rst_n), .I_rd_en(stream_valid[0]),
        .O_rd_data(stream_data[0]), .O_rd_empty(a0_empty)
    );
    assign stream_valid[0] = !a0_empty && room[0];

    wire a1_cfg_rst_n, a1_scl_drive, a1_configured;
    vid007_camera_board_adapter_a0 u_a1_board (
        .I_cfg_clk(cam_24m), .I_pll_locked(ui_pll_lock),
        .I_scl_drive(a1_scl_drive), .O_scl_od(a1_scl),
        .O_xclr_od(a1_reset), .O_sensor_cfg_rstn(a1_cfg_rst_n)
    );
    ui_cfg_imx415 #(.CLK_DIV(239)) u_a1_cfg (
        .I_clk(cam_24m), .I_rst_n(a1_cfg_rst_n), .I_ae_req(1'b0), .I_ae_data(0),
        .O_cam_scl(a1_scl_drive), .IO_cam_sda(a1_sda), .O_cfg_done(a1_configured)
    );
    wire [39:0] a1_raw;
    wire a1_valid, a1_sof, a1_eol, a1_done, a1_good;
    vid008_rx_isp_adapter u_a1_rx (
        .I_rx_clk(cam_pclk), .I_rstn(ui_pll_lock), .I_cfg_done(a1_configured),
        .I_cam_clk_p(a1_clk), .I_cam_d_p(a1_data),
        .O_valid(a1_valid), .O_data(a1_raw), .O_sof(a1_sof), .O_eol(a1_eol),
        .O_frame_done(a1_done), .O_frame_good(a1_good)
    );
    wire [8:0] a1_fifo_in;
    wire a1_push, a1_full, a1_empty;
    vid007_gray u_a1_gray (
        .clk(cam_pclk), .rst_n(rx_stream_rst_n), .valid(a1_valid),
        .sof(a1_sof), .eol(a1_eol), .raw10(a1_raw),
        .frame_done(a1_done), .frame_good(a1_good),
        .full(a1_full), .push(a1_push), .data(a1_fifo_in)
    );
    dphy_raw_async_fifo #(.WIDTH(9), .AW(10)) u_a1_fifo (
        .I_wr_clk(cam_pclk), .I_wr_rstn(rx_stream_rst_n), .I_wr_en(a1_push),
        .I_wr_data(a1_fifo_in), .O_wr_full(a1_full),
        .I_rd_clk(user_clk), .I_rd_rstn(stream_rst_n), .I_rd_en(stream_valid[1]),
        .O_rd_data(stream_data[1]), .O_rd_empty(a1_empty)
    );
    assign stream_valid[1] = !a1_empty && room[1];

    wire b0_cfg_rst_n, b0_scl_drive, b0_configured;
    vid007_camera_board_adapter_b0 u_b0_board (
        .I_cfg_clk(cam_24m), .I_pll_locked(ui_pll_lock),
        .I_scl_drive(b0_scl_drive), .O_scl_od(b0_scl),
        .O_xclr_od(b0_reset), .O_sensor_cfg_rstn(b0_cfg_rst_n)
    );
    ui_cfg_imx415 #(.CLK_DIV(239)) u_b0_cfg (
        .I_clk(cam_24m), .I_rst_n(b0_cfg_rst_n), .I_ae_req(1'b0), .I_ae_data(0),
        .O_cam_scl(b0_scl_drive), .IO_cam_sda(b0_sda), .O_cfg_done(b0_configured)
    );
    wire [39:0] b0_raw;
    wire b0_valid, b0_sof, b0_eol, b0_done, b0_good;
    vid008_rx_isp_adapter u_b0_rx (
        .I_rx_clk(cam_pclk), .I_rstn(ui_pll_lock), .I_cfg_done(b0_configured),
        .I_cam_clk_p(b0_clk), .I_cam_d_p(b0_data),
        .O_valid(b0_valid), .O_data(b0_raw), .O_sof(b0_sof), .O_eol(b0_eol),
        .O_frame_done(b0_done), .O_frame_good(b0_good)
    );
    wire [8:0] b0_fifo_in;
    wire b0_push, b0_full, b0_empty;
    vid007_gray u_b0_gray (
        .clk(cam_pclk), .rst_n(rx_stream_rst_n), .valid(b0_valid),
        .sof(b0_sof), .eol(b0_eol), .raw10(b0_raw),
        .frame_done(b0_done), .frame_good(b0_good),
        .full(b0_full), .push(b0_push), .data(b0_fifo_in)
    );
    dphy_raw_async_fifo #(.WIDTH(9), .AW(10)) u_b0_fifo (
        .I_wr_clk(cam_pclk), .I_wr_rstn(rx_stream_rst_n), .I_wr_en(b0_push),
        .I_wr_data(b0_fifo_in), .O_wr_full(b0_full),
        .I_rd_clk(user_clk), .I_rd_rstn(stream_rst_n), .I_rd_en(stream_valid[2]),
        .O_rd_data(stream_data[2]), .O_rd_empty(b0_empty)
    );
    assign stream_valid[2] = !b0_empty && room[2];

    wire b1_cfg_rst_n, b1_scl_drive, b1_configured;
    vid007_camera_board_adapter_b0 u_b1_board (
        .I_cfg_clk(cam_24m), .I_pll_locked(ui_pll_lock),
        .I_scl_drive(b1_scl_drive), .O_scl_od(b1_scl),
        .O_xclr_od(b1_reset), .O_sensor_cfg_rstn(b1_cfg_rst_n)
    );
    ui_cfg_imx415 #(.CLK_DIV(239)) u_b1_cfg (
        .I_clk(cam_24m), .I_rst_n(b1_cfg_rst_n), .I_ae_req(1'b0), .I_ae_data(0),
        .O_cam_scl(b1_scl_drive), .IO_cam_sda(b1_sda), .O_cfg_done(b1_configured)
    );
    wire [39:0] b1_raw;
    wire b1_valid, b1_sof, b1_eol, b1_done, b1_good;
    vid008_rx_isp_adapter u_b1_rx (
        .I_rx_clk(cam_pclk), .I_rstn(ui_pll_lock), .I_cfg_done(b1_configured),
        .I_cam_clk_p(b1_clk), .I_cam_d_p(b1_data),
        .O_valid(b1_valid), .O_data(b1_raw), .O_sof(b1_sof), .O_eol(b1_eol),
        .O_frame_done(b1_done), .O_frame_good(b1_good)
    );
    wire [8:0] b1_fifo_in;
    wire b1_push, b1_full, b1_empty;
    vid007_gray u_b1_gray (
        .clk(cam_pclk), .rst_n(rx_stream_rst_n), .valid(b1_valid),
        .sof(b1_sof), .eol(b1_eol), .raw10(b1_raw),
        .frame_done(b1_done), .frame_good(b1_good),
        .full(b1_full), .push(b1_push), .data(b1_fifo_in)
    );
    dphy_raw_async_fifo #(.WIDTH(9), .AW(10)) u_b1_fifo (
        .I_wr_clk(cam_pclk), .I_wr_rstn(rx_stream_rst_n), .I_wr_en(b1_push),
        .I_wr_data(b1_fifo_in), .O_wr_full(b1_full),
        .I_rd_clk(user_clk), .I_rd_rstn(stream_rst_n), .I_rd_en(stream_valid[3]),
        .O_rd_data(stream_data[3]), .O_rd_empty(b1_empty)
    );
    assign stream_valid[3] = !b1_empty && room[3];
sgdma_app #(
    .ODATA_WIDTH    (DATA_WIDTH),
    .OKEEP_WIDTH    (KEEP_WIDTH),
    .H2C_CHNL_NUM  (H2C_CHNL_NUM),
    .H2C_DSC_BYP_MAP(H2C_DSC_BYP_MAP),
    .C2H_CHNL_NUM  (C2H_CHNL_NUM),
    .C2H_DSC_BYP_MAP(C2H_DSC_BYP_MAP),
    .DESC_BYP_EN   (DESC_BYP_EN)
) u_sgdma_app(
    .usr_rst_n                  (user_rst_n),
    .usr_clk                    (user_clk),
`ifdef AXI4ST_BUS_EN
    .m0_axis_h2c_tready         (m0_axis_h2c_tready),
    .m0_axis_h2c_tdata          (m0_axis_h2c_tdata),
    .m0_axis_h2c_tkeep          (m0_axis_h2c_tkeep),
    .m0_axis_h2c_tuser          (m0_axis_h2c_tuser),
    .m0_axis_h2c_tlast          (m0_axis_h2c_tlast),
    .m0_axis_h2c_tvalid         (m0_axis_h2c_tvalid),
    .s0_axis_c2h_tready         (app_c2h_tready),
    .s0_axis_c2h_tdata          (app_c2h_tdata),
    .s0_axis_c2h_tkeep          (app_c2h_tkeep),
    .s0_axis_c2h_tuser          (app_c2h_tuser),
    .s0_axis_c2h_tlast          (app_c2h_tlast),
    .s0_axis_c2h_tvalid         (app_c2h_tvalid),
`endif
`ifdef AXI4L_MBUS_EN
    .m_axil_awaddr              (m_axil_awaddr),
    .m_axil_awprot              (m_axil_awprot),
    .m_axil_awvalid             (m_axil_awvalid),
    .m_axil_awready             (m_axil_awready),
    .m_axil_wdata               (m_axil_wdata),
    .m_axil_wstrb               (m_axil_wstrb),
    .m_axil_wvalid              (m_axil_wvalid),
    .m_axil_wready              (m_axil_wready),
    .m_axil_bvalid              (m_axil_bvalid),
    .m_axil_bresp               (m_axil_bresp),
    .m_axil_bready              (m_axil_bready),
    .m_axil_araddr              (m_axil_araddr),
    .m_axil_arprot              (m_axil_arprot),
    .m_axil_arvalid             (m_axil_arvalid),
    .m_axil_arready             (m_axil_arready),
    .m_axil_rdata               (app_axil_rdata),
    .m_axil_rresp               (m_axil_rresp),
    .m_axil_rvalid              (m_axil_rvalid),
    .m_axil_rready              (m_axil_rready),
`endif
`ifdef DSC_BYPASS_C2H_CHL0_EN
    .c2h_dsc_byp_ready_0_i     (c2h_dsc_byp_ready_0),
    .c2h_dsc_byp_load_0_o      (c2h_dsc_byp_load_0),
    .c2h_dsc_byp_src_addr_0_o  (c2h_dsc_byp_src_addr_0),
    .c2h_dsc_byp_dst_addr_0_o  (c2h_dsc_byp_dst_addr_0),
    .c2h_dsc_byp_len_0_o       (c2h_dsc_byp_len_0),
    .c2h_dsc_byp_ctl_0_o       (c2h_dsc_byp_ctl_0),
`endif
`ifdef DSC_BYPASS_H2C_CHL0_EN
    .h2c_dsc_byp_ready_0_i     (h2c_dsc_byp_ready_0),
    .h2c_dsc_byp_load_0_o      (h2c_dsc_byp_load_0),
    .h2c_dsc_byp_src_addr_0_o  (h2c_dsc_byp_src_addr_0),
    .h2c_dsc_byp_dst_addr_0_o  (h2c_dsc_byp_dst_addr_0),
    .h2c_dsc_byp_len_0_o       (h2c_dsc_byp_len_0),
    .h2c_dsc_byp_ctl_0_o       (h2c_dsc_byp_ctl_0),
`endif
`ifdef USR_IRQ_EN
    .usr_irq_req                (usr_irq_req),
    .usr_irq_ack                (usr_irq_ack),
    .msi_enable                 (msi_enable),
    .msi_vector_width           (msi_vector_width),
`endif
    .c2h_sts_0                  (c2h_sts_0),
    .h2c_sts_0                  (h2c_sts_0),
    .c2h_sts_1                  (c2h_sts_1),
    .h2c_sts_1                  (h2c_sts_1),
    .c2h_sts_2                  (c2h_sts_2),
    .h2c_sts_2                  (h2c_sts_2),
    .c2h_sts_3                  (c2h_sts_3),
    .h2c_sts_3                  (h2c_sts_3)
);


endmodule
