`timescale 1ns / 1ps
// pad_ddr - the AFC03 core board's DDR3L (256 MB, x16, DDR3-1066) for the PAD cerebellum.
//
// Anlogic DDR IP `ui_ddr` (generated for this board by Milianke, uisrc/03_ip/ui_ddr, AXI4 128 bit on dfi_clk =
// 133 MHz) + Milianke `ui_FDMA` (simple request/size/busy DMA ports on dfi_clk) + pad_ddr_selftest.
// Connections follow the vendor demo 04_ddr3_axi_fdma_test (system_top.v) port for port.
// The FDMA user channels are driven by the self-test (sel_user = 0) or by the PAD frame history (sel_user = 1).
// Everything on the user side is in the dfi_clk domain; dfi_clk and cal_done are outputs.
module pad_ddr #(
    parameter AW = 30,                      // FDMA byte address width (the IP uses the low 28 bits = 256 MB)
    parameter SELFTEST = 1                  // 0: no self-test (st_* outputs read 0, done never set); the FDMA serves the user channels only
) (
    input  wire          sys_clk,            // 100 MHz from a BUFG
    // DDR3 pins
    output wire [13:0]   ddr_addr,
    output wire [2:0]    ddr_ba,
    output wire [0:0]    ddr_cke,
    output wire [0:0]    ddr_odt,
    output wire [0:0]    ddr_cs_n,
    output wire          ddr_ras_n,
    output wire          ddr_cas_n,
    output wire          ddr_we_n,
    output wire          ddr_ck_p,
    output wire          ddr_ck_n,
    output wire          ddr_reset_n,
    inout  wire [1:0]    ddr_dm,
    inout  wire [15:0]   ddr_dq,
    inout  wire [1:0]    ddr_dqs_n,
    inout  wire [1:0]    ddr_dqs_p,
    // status (dfi_clk domain)
    output wire          dfi_clk,
    output wire          pll_locked,
    output wire          cal_done,
    output wire [7:0]    cal_err,
    output wire [7:0]    cal_step,
    // self-test (dfi_clk domain)
    input  wire          st_start,
    input  wire [1:0]    st_mode,
    input  wire [AW-1:0] st_base,
    input  wire [23:0]   st_nreq,
    input  wire [31:0]   st_seed,
    output wire          st_busy,
    output wire          st_done,
    output wire [31:0]   st_err_cnt,
    output wire [AW-1:0] st_first_err,
    output wire [31:0]   st_wr_cycles,
    output wire [31:0]   st_rd_cycles,
    output wire [31:0]   st_rd_words,
    // user FDMA channels (dfi_clk domain), used when sel_user = 1
    input  wire          sel_user,
    input  wire [AW-1:0] u_waddr,
    input  wire          u_wareq,
    input  wire [15:0]   u_wsize,
    output wire          u_wbusy,
    input  wire [127:0]  u_wdata,
    output wire          u_wvalid,
    output wire          u_werror,
    output wire [1:0]    u_werror_camera,
    input  wire [AW-1:0] u_raddr,
    input  wire          u_rareq,
    input  wire [15:0]   u_rsize,
    output wire          u_rbusy,
    output wire [127:0]  u_rdata,
    output wire          u_rvalid
);
    localparam IDW = 4;

    // ---------------- self-test ----------------
    wire [AW-1:0] t_waddr, t_raddr;
    wire          t_wareq, t_rareq;
    wire [15:0]   t_wsize, t_rsize;
    wire [127:0]  t_wdata;
    wire          f_wbusy, f_wvalid, f_rbusy, f_rvalid;
    wire [127:0]  f_rdata;

    generate if (SELFTEST) begin : g_st
    pad_ddr_selftest #(.AW(AW), .BURST(1024)) u_st (
        .clk(dfi_clk), .rst_n(cal_done),
        .start(st_start), .mode(st_mode), .base(st_base), .nreq(st_nreq), .seed(st_seed),
        .busy(st_busy), .done(st_done), .err_cnt(st_err_cnt), .first_err(st_first_err),
        .wr_cycles(st_wr_cycles), .rd_cycles(st_rd_cycles), .rd_words(st_rd_words),
        .waddr(t_waddr), .wareq(t_wareq), .wsize(t_wsize), .wbusy(f_wbusy & ~sel_user), .wdata(t_wdata),
        .wvalid(f_wvalid & ~sel_user),
        .raddr(t_raddr), .rareq(t_rareq), .rsize(t_rsize), .rbusy(f_rbusy & ~sel_user), .rdata(f_rdata),
        .rvalid(f_rvalid & ~sel_user)
    );
    end else begin : g_no_st
    // no requests from the self-test side: with sel_user = 0 the FDMA simply idles
    assign t_waddr = {AW{1'b0}}, t_raddr = {AW{1'b0}}, t_wareq = 1'b0, t_rareq = 1'b0;
    assign t_wsize = 16'd0, t_rsize = 16'd0, t_wdata = 128'd0;
    assign st_busy = 1'b0, st_done = 1'b0, st_err_cnt = 32'd0, st_first_err = {AW{1'b0}};
    assign st_wr_cycles = 32'd0, st_rd_cycles = 32'd0, st_rd_words = 32'd0;
    end endgenerate

    // ---------------- channel select ----------------
    wire [AW-1:0] m_waddr = sel_user ? u_waddr : t_waddr;
    wire          m_wareq = sel_user ? u_wareq : t_wareq;
    wire [15:0]   m_wsize = sel_user ? u_wsize : t_wsize;
    wire [127:0]  m_wdata = sel_user ? u_wdata : t_wdata;
    wire [AW-1:0] m_raddr = sel_user ? u_raddr : t_raddr;
    wire          m_rareq = sel_user ? u_rareq : t_rareq;
    wire [15:0]   m_rsize = sel_user ? u_rsize : t_rsize;
    assign u_wbusy  = f_wbusy  & sel_user;
    assign u_wvalid = f_wvalid & sel_user;
    assign u_rbusy  = f_rbusy  & sel_user;
    assign u_rvalid = f_rvalid & sel_user;
    assign u_rdata  = f_rdata;

    // ---------------- FDMA -> AXI4 ----------------
    wire [IDW-1:0] awid, arid, bid, rid;
    wire [AW-1:0]  awaddr, araddr;
    wire [7:0]     awlen, arlen;
    wire [2:0]     awsize, arsize, awprot, arprot;
    wire [1:0]     awburst, arburst, bresp, rresp;
    wire           awlock, arlock;
    wire [3:0]     awcache, arcache, awqos, arqos;
    wire           awvalid, awready, wvalid, wready, wlast, bvalid, bready, arvalid, arready, rvalid, rready, rlast;
    wire [127:0]   wdata, rdata;
    wire [15:0]    wstrb;
    wire [IDW-1:0] wid_unused;

    // FDMA uses one AXI ID. Keep its accepted burst ownership until the
    // corresponding response, even when a response crosses a camera switch.
    reg [1:0] response_camera [0:63];
    reg [6:0] request_index, response_index;
    wire response_room = request_index != (response_index ^ 7'd64);
    wire write_address_accepted = awvalid && awready && response_room;
    wire response_present = response_index != request_index;
    assign u_werror = response_present && bvalid && bready && bresp[1] && sel_user;
    assign u_werror_camera = response_camera[response_index[5:0]];

    always @(posedge dfi_clk) begin
        if (write_address_accepted)
            response_camera[request_index[5:0]] <= awaddr[25:24];
    end
    always @(posedge dfi_clk or negedge cal_done) begin
        if (!cal_done) begin
            request_index <= 0;
            response_index <= 0;
        end else begin
            if (write_address_accepted) request_index <= request_index + 1'b1;
            if (response_present && bvalid && bready) response_index <= response_index + 1'b1;
        end
    end

    ui_FDMA #(
        .M_AXI_B2B_SET(1), .M_AXI_ID_WIDTH(IDW), .M_AXI_ADDR_WIDTH(AW), .M_AXI_DATA_WIDTH(128), .M_AXI_MAX_BURST_LEN(16)
    ) u_fdma (
        .I_fdma_waddr(m_waddr), .I_fdma_wareq(m_wareq), .I_fdma_wsize(m_wsize), .O_fdma_wbusy(f_wbusy),
        .I_fdma_wdata(m_wdata), .O_fdma_wvalid(f_wvalid), .I_fdma_wready(1'b1),
        .I_fdma_raddr(m_raddr), .I_fdma_rareq(m_rareq), .I_fdma_rsize(m_rsize), .O_fdma_rbusy(f_rbusy),
        .O_fdma_rdata(f_rdata), .O_fdma_rvalid(f_rvalid), .I_fdma_rready(1'b1),
        .M_AXI_ACLK(dfi_clk), .M_AXI_ARESETN(cal_done),
        .M_AXI_AWID(awid), .M_AXI_AWADDR(awaddr), .M_AXI_AWLEN(awlen), .M_AXI_AWSIZE(awsize), .M_AXI_AWBURST(awburst),
        .M_AXI_AWLOCK(awlock), .M_AXI_AWCACHE(awcache), .M_AXI_AWPROT(awprot), .M_AXI_AWQOS(awqos),
        .M_AXI_AWVALID(awvalid), .M_AXI_AWREADY(awready && response_room),
        .M_AXI_WID(wid_unused), .M_AXI_WDATA(wdata), .M_AXI_WSTRB(wstrb), .M_AXI_WLAST(wlast), .M_AXI_WVALID(wvalid),
        .M_AXI_WREADY(wready),
        .M_AXI_BID(bid), .M_AXI_BRESP(bresp), .M_AXI_BVALID(bvalid), .M_AXI_BREADY(bready),
        .M_AXI_ARID(arid), .M_AXI_ARADDR(araddr), .M_AXI_ARLEN(arlen), .M_AXI_ARSIZE(arsize), .M_AXI_ARBURST(arburst),
        .M_AXI_ARLOCK(arlock), .M_AXI_ARCACHE(arcache), .M_AXI_ARPROT(arprot), .M_AXI_ARQOS(arqos),
        .M_AXI_ARVALID(arvalid), .M_AXI_ARREADY(arready),
        .M_AXI_RID(rid), .M_AXI_RDATA(rdata), .M_AXI_RRESP(rresp), .M_AXI_RLAST(rlast), .M_AXI_RVALID(rvalid),
        .M_AXI_RREADY(rready)
    );

    // ---------------- DDR controller + PHY (vendor IP) ----------------
    ui_ddr u_ddr (
        .sys_rst_n(1'b1), .sys_clk(sys_clk),
        .ddr_ck_p(ddr_ck_p), .ddr_ck_n(ddr_ck_n), .ddr_reset_n(ddr_reset_n), .ddr_cke(ddr_cke), .ddr_odt(ddr_odt),
        .ddr_cs_n(ddr_cs_n), .ddr_ras_n(ddr_ras_n), .ddr_cas_n(ddr_cas_n), .ddr_we_n(ddr_we_n), .ddr_ba(ddr_ba),
        .ddr_addr(ddr_addr), .ddr_dqs_p(ddr_dqs_p), .ddr_dqs_n(ddr_dqs_n), .ddr_dq(ddr_dq), .ddr_dm(ddr_dm),
        .ctl_ram_rst_n(), .ctl_ram_cke(),
        .dfi_clk(dfi_clk), .pll_locked(pll_locked), .ddrphy_rst_n(), .ddr_init_cal_done(cal_done),
        .ddr_init_cal_err(cal_err), .ddr_init_cal_step(cal_step),
        .axi_aclk(), .axi_aresetn(),
        .axi_awid(awid), .axi_awaddr(awaddr[27:0]), .axi_awlen(awlen), .axi_awsize(awsize), .axi_awburst(awburst),
        .axi_awlock(awlock), .axi_awcache(awcache), .axi_awprot(awprot), .axi_awqos(awqos), .axi_awvalid(awvalid && response_room),
        .axi_awready(awready),
        .axi_wdata(wdata), .axi_wstrb(wstrb), .axi_wlast(wlast), .axi_wvalid(wvalid), .axi_wready(wready),
        .axi_bid(bid), .axi_bresp(bresp), .axi_bvalid(bvalid), .axi_bready(bready),
        .axi_arid(arid), .axi_araddr(araddr[27:0]), .axi_arlen(arlen), .axi_arsize(arsize), .axi_arburst(arburst),
        .axi_arlock(arlock), .axi_arcache(arcache), .axi_arprot(arprot), .axi_arqos(arqos), .axi_arvalid(arvalid),
        .axi_arready(arready),
        .axi_rid(rid), .axi_rdata(rdata), .axi_rresp(rresp), .axi_rlast(rlast), .axi_rvalid(rvalid), .axi_rready(rready),
        .uart_rxd(1'b1), .uart_txd()
    );
endmodule
