<?xml version='1.0' encoding='UTF-8'?>
<Project Version="3" Minor="2" Path=".">
  <Project_Created_Time />
  <TD_Version>6.2.200067</TD_Version>
  <Name>vid007_hdr_quiesce</Name>
  <HardWare>
    <Family>PH1</Family>
    <Device>PH1A90SEG324</Device>
    <Speed>-2</Speed>
  </HardWare>
  <MiscSettings>
    <Setting Key="farm" Val="disable" />
  </MiscSettings>
  <Source_Files>
    <Verilog>
      <File Path="uisrc/01_rtl/para_def.vh">
        <FileInfo>
          <Attr Name="GlobalIncluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="1" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/src_enc/sgdma_ip_all.enc.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="4" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/top/ph2_pcie_rst_sync.v">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="5" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_subsys.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="6" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/top/pcie_brg_clk_rst.v">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="81" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/top/pcie_brg_top.v">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="82" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/axil_anal.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="83" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/desc_anal.v">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="84" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/desc_byp_channel_block.v">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="85" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/ram_wrapper.v">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="86" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/sgdma_app.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="87" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/usr_axi4mmb.v">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="88" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/usr_axi4mmlp.v">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="89" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/usr_axi4mmr.v">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="90" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/usr_axi4mmw.v">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="91" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/usr_axi4st_c2h.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="92" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/usr_axi4st_h2c.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="93" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/usr_axi4st_lp.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="94" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/usr_cfgrw.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="95" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/usr_ctrl.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="96" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/usr_dmarw.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="97" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/sgdma_app/src/usr_irq.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="98" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/case_ep/al_pcie_if_ep.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="123" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/tx_if/axi4_st_mux.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="124" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/tx_if/pcie_tx_client02rq_new.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="125" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/tx_if/pcie_tx_client12cc.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="126" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/rx_if/pcie_rx_bypass2rc.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="127" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/rx_if/pcie_rx_trgt2cq.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="128" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/sideband_if/pcie_sideband_dbi2mgmt.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="129" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v1_ph1/al_pcie_if/sideband_if/pcie_sideband_msi.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="130" />
        </FileInfo>
      </File>
      <File Path="fork_hwm/pcie_jpg_mux.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="142" />
        </FileInfo>
      </File>
      <File Path="fork_hwm/pcie_jpg_mux4.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="156" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_rx/alignment/dphy_hs_lane_aligner.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="400" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_rx/alignment/dphy_lane_deskew.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="401" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/mipi_rx/core/mipi_rx_top.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="402" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_rx/interface/mipi_csi2_stream_guard.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="403" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/mipi_rx/interface/mipi_rx_ip_top.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="404" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_rx/phy/dphy_hs_clk_lane.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="405" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_rx/phy/dphy_hs_data_lane.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="406" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_rx/phy/dphy_raw_async_fifo.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="407" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_rx/phy/dphy_rst_sync.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="408" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_rx/protocol/csi2_crc16_x32.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="409" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_rx/protocol/csi2_frame_observer.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="410" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_rx/protocol/csi2_header_ecc.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="411" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/mipi_rx/protocol/csi2_packet_checker.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="412" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_rx/training/dphy_lane_calibrator.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="413" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/ui_imx415_cfg/ui_cfg_imx415.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="414" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/ui_imx415_cfg/ui_i2c.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="415" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/ui_imx415_cfg/ui_imx415_reg.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="416" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/dphy_fault_trace.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="417" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/mipi_raw10_crop.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="418" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/vid008_rx_isp_adapter.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="419" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/vid007_camera_board_adapter_a0.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="420" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/vid007_camera_board_adapter_b0.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="421" />
        </FileInfo>
      </File>
      <File Path="vid007_measure/vid007_switch.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="422" />
        </FileInfo>
      </File>
      <File Path="vid007_measure/vid007_clahe.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="434" />
        </FileInfo>
      </File>
      <File Path="vid007_measure/vid007_subpixel.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="435" />
        </FileInfo>
      </File>
      <File Path="vid007_measure/pp_sdp_dram.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="436" />
        </FileInfo>
      </File>
      <File Path="vid007_advanced/pad_ddr.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="423" />
        </FileInfo>
      </File>
      <File Path="vid007_ddr_preview/pad_afifo.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="424" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/uifdma/uiFDMA.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="425" />
        </FileInfo>
      </File>
      <File Path="vid007_resolution/vid007_ddr_capture.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="426" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/vid007_ddr_stream.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="427" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/vid007_jpeg_capture.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="437" />
        </FileInfo>
      </File>
      <File Path="vid007_jpeg_pipe/vid007_jpeg_channel.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="438" />
        </FileInfo>
      </File>
      <File Path="vid007_jpeg_pipe/vid007_jpeg_predict.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="439" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/vid007_jpeg_entropy.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="440" />
        </FileInfo>
      </File>
      <File Path="vid007_jpeg_pipe/vid007_jpeg_blocks.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="441" />
        </FileInfo>
      </File>
      <File Path="vid007_advanced/vid007_metrics.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="429" />
        </FileInfo>
      </File>
      <File Path="vid007_resolution/vid007_decimate.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="433" />
        </FileInfo>
      </File>
      <File Path="vid007_jpeg_pipe/vid007_pixel_ops.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="430" />
        </FileInfo>
      </File>
      <File Path="vid007_advanced/pp_histeq.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="431" />
        </FileInfo>
      </File>
      <File Path="vid007_advanced/pp_sdp_ram.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="432" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/vid007_top.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="428" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/vid007_hdr_raw12.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="444" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/vid007_hdr_pair.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="445" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/vid007_hdr_merge.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="446" />
        </FileInfo>
      </File>
      <File Path="vid007_hdr_quiesce/vid007_hdr_csi.v">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="447" />
        </FileInfo>
      </File>
    </Verilog>
    <System_Verilog>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_bdf_dec.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="13" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_bdf_enc.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="14" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_cdc_bus_sync.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="16" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_cdc_gray.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="18" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_cdc_handshake.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="20" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_cdc_sync.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="22" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_cfg_ctrl.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="24" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_cfg_flow_ctrl.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="26" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_cfg_mgmt.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="28" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_cfg_status.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="30" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_cq_rc_demux.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="32" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_cq_rc_enc.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="34" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_def.svh">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="36" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_fifo.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="38" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_int.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="40" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_mon_np_cpl.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="42" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_mon_rq.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="44" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_mon.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="46" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_recv_msg.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="48" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_reg_slice.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="50" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_rq_cc_dec.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="52" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_rq_cc_mux.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="55" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_rx_dec.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="57" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_rx_demux.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="59" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_rx_width_conv.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="61" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_rx.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="63" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_tx_enc.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="65" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_tx_mux.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="67" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_tx_width_conv.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="69" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_tx.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="71" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_wrapper.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="73" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg_xmit_msg.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="75" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/sgdma/pcie_bridge/bridge_v2/rtl/core/pcie_brg.sv">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="80" />
        </FileInfo>
      </File>
    </System_Verilog>
    <ADC_FILE>
      <File Path="vid007_hdr_quiesce/vid007.adc">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="constraint_1" />
          <Attr Name="CompileOrder" Val="1" />
        </FileInfo>
      </File>
    </ADC_FILE>
    <SDC_FILE>
      <File Path="vid007_hdr_quiesce/vid007.sdc">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="constraint_1" />
          <Attr Name="CompileOrder" Val="1" />
        </FileInfo>
      </File>
    </SDC_FILE>
    <IP_FILE>
      <File Path="al_ip/pcie_brg_pcie_core/pcie_brg_pcie_core.ipc">
        <FileInfo>
          <Attr Name="AutoExcluded" Val="true" />
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="99" />
        </FileInfo>
      </File>
      <File Path="al_ip/PH1_LOGIC_PCIE.ipc">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="121" />
        </FileInfo>
      </File>
      <File Path="al_ip/sgdma_pll.ipc">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="131" />
        </FileInfo>
      </File>
      <File Path="al_ip/ui_pll.ipc">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="132" />
        </FileInfo>
      </File>
      <File Path="uisrc/03_ip/ui_ddr/ui_ddr.ipc">
        <FileInfo>
          <Attr Name="UsedInSyn" Val="true" />
          <Attr Name="UsedInP&R" Val="true" />
          <Attr Name="BelongTo" Val="design_1" />
          <Attr Name="CompileOrder" Val="202" />
        </FileInfo>
      </File>
    </IP_FILE>
  </Source_Files>
  <FileSets>
    <FileSet Name="design_1" Type="DesignFiles">
        </FileSet>
    <FileSet Name="constraint_1" Type="ConstrainFiles">
        </FileSet>
  </FileSets>
  <TOP_MODULE>
    <LABEL>vid007_top</LABEL>
    <MODULE>vid007_top</MODULE>
    <CREATEINDEX>user</CREATEINDEX>
  </TOP_MODULE>
  <Property>
    </Property>
  <Device_Settings>
    </Device_Settings>
  <Configurations>
    </Configurations>
  <Runs>
    <Run Name="syn_1" Type="Synthesis" ConstraintSet="constraint_1" Description="" Active="true">
      <Strategy Name="Default_Synthesis_Strategy">
            </Strategy>
      <UserParams>
            </UserParams>
    </Run>
    <Run Name="phy_1" Type="PhysicalDesign" ConstraintSet="constraint_1" Description="" SynRun="syn_1" Active="true">
      <Strategy Name="Default_PhysicalDesign_Strategy">
        <BitgenProperty::GeneralOption>
          <compress>on</compress>
        </BitgenProperty::GeneralOption>
      </Strategy>
      <UserParams>
        <param>set_param flow bad_qor_check off</param>
      </UserParams>
    </Run>
  </Runs>
  <MultiSeed>
    <Property Enable="true" GenBit="true" EndStep="route" Random="false" Num="4" Init="1" Jobs="4" Save="1" Step="7">
      <Filter enabled="false">
        <congestion>100</congestion>
        <place_swns>0</place_swns>
        <route_swns>0</route_swns>
      </Filter>
    </Property>
    <Seeds select="1">1 8 15 22 </Seeds>
  </MultiSeed>
  <Project_Settings>
    </Project_Settings>
</Project>
