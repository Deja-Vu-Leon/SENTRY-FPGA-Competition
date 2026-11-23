# 慧行智瞳 v2.0 部署

| 目录 | 内容 |
| --- | --- |
| `FPGA/prj/isp_imx415/` | VID007 集成 RTL、约束和安路 TD 项目描述 |
| `RK/bringup/rk-ai/` | RK3568 的 F1–F7 界面、感知、录像及图像校准 |
| `ESP32/` | ESP-IDF 网关、网页、协议、RK 后台及 PC 客户端 |
| `launcher/` | Windows 一键启动器及构建脚本 |
| `adas_vision_pcie/` | 原双路应用与 RK 侧共用检测逻辑 |

## FPGA

本仓库的 FPGA 部分是对配套工程的集成层。将 `FPGA/prj/isp_imx415/` 中的文件按原相对位置叠加到已获授权的板卡工程，并提供 FMC-VID007 的摄像头接收 IP、基础 ISP RTL 和 PCIe IP。打开 `vid007_hdr_quiesce.al`。若 TD 要求工程路径，编辑项目文件首行 `Project` 元素的 `Path` 指向本机工程目录。综合、布局布线及检查时序后生成 `vid007_hdr_quiesce.bit` 和 `vid007_hdr_quiesce.timing`。发版使用的 FPGA 接口版本为 `0x5607040E`。

## RK3568

将 `RK/bringup/` 放到 RK 的 `/home/linaro/sentry-vid007/`。在 `/home/linaro/sentry-dual/` 准备原双路版的 `vision.py` 和 `vehicle_risk.py`，以及与板卡匹配的 `rk_yolo_srv`、`yolov8n.rknn`。配套 DMA 驱动应位于 `/home/linaro/sentry-vid007/pcie-ring-batch/anlogic_pci_ring.ko`。使用板卡 BSP 中对应 RK 内核和 NPU 的二进制。

在 RK 安装 OpenCV、NumPy、ONNX Runtime、GStreamer（含 Rockchip MPP）、FFmpeg、libdrm、FreeType 和 C/C++ 工具链。按上游许可准备 `rk-ai/models/` 的 OpenCV 人脸与眼睛级联模型、滑坡与裂缝 ONNX 权重。具体名称见 `cockpit_worker.py` 和 `hazard_model.py`。F7 拼音适配器需要从 Debian [libgooglepinyin 源码包](https://tracker.debian.org/pkg/libgooglepinyin)准备开发库和生成的 `dict_pinyin.dat`。词库默认位于 `/home/linaro/sentry-esp32/ime/`。

在 `/home/linaro/sentry-vid007/rk-ai` 编译界面：

```sh
g++ -std=c++11 -O2 -c /path/to/sentry-pinyin.cpp -o /tmp/sentry-pinyin.o
gcc -O3 -march=armv8-a -DHDMI -DKMS -I.. \
  $(pkg-config --cflags libdrm freetype2 libavcodec libavutil) \
  -c vid007-cockpit-preview.c -o /tmp/sentry-preview.o
g++ /tmp/sentry-preview.o /tmp/sentry-pinyin.o -lgooglepinyin \
  $(pkg-config --libs libdrm freetype2 libavcodec libavutil) \
  -pthread -lm -o vid007-cockpit-preview
sudo bash start-rk-cockpit.sh
```

## ESP32-P4-NANO

使用 ESP-IDF 6.0.2 和兼容 ESP-Hosted 的板载 C6 固件。在 `ESP32/` 中执行 `idf.py set-target esp32p4`，通过 `idf.py menuconfig` 设置自己的网关访问令牌，再执行 `idf.py build`。未设置令牌时 API 拒绝访问。AP 密码留空时热点关闭，可只使用直连网口或上游 Wi-Fi。烧录后从可信的直连网口使用 [协议](ESP32/PROTOCOL.md)配置上游 Wi-Fi 和 DeepSeek API Key，也可用 `ESP32/tools/gateway_client.py` 的 `configure` 命令提交仅保存在本地的 JSON 文件。请将设备配置、密钥和包含私有配置的构建产物保留在本机。

网口默认 ESP32 为 `192.168.50.1/24`，RK 的直连接口为 `192.168.50.2/24`，另保留 RK 与 PC 的管理网口。将 `ESP32/tools/` 中的 Python 程序和 systemd 服务按文件里的路径部署。客户端通过 `SENTRY_ACCESS_TOKEN` 或显式参数读取令牌。若启用 Windows 启动器的 RK 自检，可在 RK 的 `/etc/sentry-esp32/access-token` 保存同一令牌，设置为 root 所有、权限 `0600`。后台服务没有专门注入环境变量时也读取该文件。

## Windows 一键程序

在仓库根目录运行 `launcher/Build.ps1`。准备 Windows OpenSSH、Python、FTDI 驱动、安路 TD 下载工具以及已配置的 SSH 公钥。保存已通过独立信道核对的 RK 主机公钥到 `RK/bringup/rk-known-hosts`，按本机环境设置 `SENTRY_RK_KEY` 和 `SENTRY_FTDI_SERIAL`。将本机构建的位流和时序文件放到 `FPGA/prj/isp_imx415/`。脚本当前使用原型板管理地址 `linaro@192.168.137.212`，其他环境可先修改 `launcher/FlashAndStart.ps1` 再编译。

先运行 `一键烧录并启动.exe --check` 核对设备状态。完整执行会启动 RK HDMI 并调用一次 DeepSeek 联网检查。发布包遵循 [第三方依赖说明](THIRD_PARTY.md)，板卡 IP、BSP、模型权重、位流、设备配置、密码与私钥由各部署环境单独提供。
