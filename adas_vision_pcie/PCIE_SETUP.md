# FPGA PCIe camera input on RK

Data path: FPGA CHNK -> Anlogic C2H DMA -> cs500_live.py -> /frame -> OpenCV BGR -> ADAS.

Use the host directory from the same FPGA release as the bitstream. The v0635b
reference platform is RK3576. On a different RK board, verify PCIe enumeration
and use an Anlogic kernel module built for the running kernel (uname -r).
Use a graphical desktop session for the Tk dashboard.

1. Program the FPGA, then on the RK check the PCIe endpoint and driver:

       lspci -nn
       uname -r
       ls -l /dev/ANLOGIC-PCI0_c2h_0

   If the module is not loaded, load the matching build as root:

       insmod ./anlogic_pci_ring.ko poll_mode=1 enable_st_c2h_credit=1

2. Copy the FPGA release's host directory to the RK. From that directory run
   the existing service as a user with DMA and BAR access. Keep a single DMA reader.

       python3 cs500_live.py

   Stop the service before reprogramming the FPGA or unbinding PCIe.

3. In a second terminal check both cameras:

       curl -fsS http://127.0.0.1:8080/api/status
       python3 rk_dual_camera_test.py --frames 5 --output /tmp/dual_camera_test

4. Copy this ADAS directory to RK, install its requirements in the ADAS Python
   environment, and run one of the following from that directory:

       python3 -m pip install -r requirements.txt
       python3 app.py --pcie-device 'http://127.0.0.1:8080/frame?cam=0'
       python3 app.py --pcie-device 'http://127.0.0.1:8080/frame?cam=1'

   cam=0 is J2 IMX415. cam=1 is J3 CS500. The dashboard uses one source per
   instance. Add --model /path/to/yolov8.rknn with the board's RKNN runtime
   installed to enable object detection. Existing video and V4L2 inputs still
   work. The first decoded image is passed to ADAS; following reads request a
   newer X-Serial. On stream loss, reselect the URL after restoring capture.

For a missing image, check the service log and /api/status first. If DMA is
present but a single camera has no fresh frames, check that camera's cable,
sensor configuration, and the matching FPGA bitstream.
