create_clock -name sys_clk -period 40 [get_ports {sys_clk}]
create_clock -name mipi_ref -period 10 [get_ports {mipi_ref_clk_p}]
create_clock -name a0_hs -period 2.2 [get_ports {a0_clk}]
create_clock -name a1_hs -period 2.2 [get_ports {a1_clk}]
create_clock -name b0_hs -period 2.2 [get_ports {b0_clk}]
create_clock -name b1_hs -period 2.2 [get_ports {b1_clk}]
derive_clocks
# Asynchronous sources cross only through CDC synchronizers and FIFOs.
set_clock_groups -asynchronous -group [get_clocks {u_ui_pll/pll_inst.clkc[0] u_ui_pll/pll_inst.clkc[2] mipi_ref}] -group [get_clocks {u_sgdma_subsys/DEVICE_IS_PH1A$u_ph1a_if_ep/PH1A_PCIE_CORE_BLK$u_al_pcie_ip/pcie_user_clk u_sgdma_subsys/DEVICE_IS_PH1A$u_ph1a_if_ep/PH1A_PCIE_CORE_BLK$u_al_pcie_ip/core_clk}] -group [get_clocks {sys_clk u_sgdma_pll/pll_inst.clkc[0] u_sgdma_pll/pll_inst.clkc[1]}] -group [get_clocks {a0_hs u_a0_rx/u_rx/u_rx/u_clk_lane/u_lclk.clkout u_a0_rx/u_rx/u_rx/u_clk_lane/u_lclk.clkdivout}] -group [get_clocks {a1_hs u_a1_rx/u_rx/u_rx/u_clk_lane/u_lclk.clkout u_a1_rx/u_rx/u_rx/u_clk_lane/u_lclk.clkdivout}] -group [get_clocks {b0_hs u_b0_rx/u_rx/u_rx/u_clk_lane/u_lclk.clkout u_b0_rx/u_rx/u_rx/u_clk_lane/u_lclk.clkdivout}] -group [get_clocks {b1_hs u_b1_rx/u_rx/u_rx/u_clk_lane/u_lclk.clkout u_b1_rx/u_rx/u_rx/u_clk_lane/u_lclk.clkdivout}]


set_clock_groups -asynchronous -group [get_clocks {u_pad_ddr/u_ddr/dfi_clk}]
