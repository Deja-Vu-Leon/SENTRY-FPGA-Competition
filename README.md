# SENTRY · FPGA 比赛

## v2.0.0 慧行智瞳

新版本新增四路 IMX415 采集、FPGA 图像预处理和 PCIe DMA、RK3568 的 F1–F7 HDMI 控制台，以及基于 ESP32-P4-NANO 的无线报警网关。原双路应用仍可从下文中的 `adas_vision_pcie/` 运行。

- **FPGA**：原始、无损及动态有损 JPEG，双曝光 HDR、CLAHE、阈值分割和亚像素边缘测量。
- **RK3568**：四路实时预览、色彩校准、逐路处理与诊断、报警归档、驾驶感知与实时 3D、TF 循环录像和回放、离线拼音输入及 DeepSeek 对话。
- **ESP32-P4**：有线接收 RK 问答和报警，Wi-Fi 连接上游 API，手机和电脑可在局域网查阅报警。
- **Windows**：支持构建一键启动器。启动器验证 JTAG、RK 和 ESP32，加载 FPGA 位流并启动板上已安装的 RK 程序。

既有板上测试中，四路 1080p 原始模式约 50 fps/路，PCIe 有效载荷约 416 MB/s。动态有损 JPEG 和双曝光 HDR 使用各自的采集与传输模式，帧率随配置和场景而变。驾驶感知告警与 3D 位置用于原型演示。

进入 [v2.0 部署说明](DEPLOY-v2.md) 查看目录、外部依赖和构建步骤。

## 原双路版本

基于安路 FPGA 和 RK3576 的双路车载视觉与风险预警系统。用于全国大学生嵌入式芯片与系统设计竞赛安路赛题三的原型与演示。

```text
双路摄像头 → 安路 PH1A90 → PCIe DMA → RK3576
  → 四点透视校正 → 图像增强 → NPU 检测和光流跟踪
  → 单目风险估计 → 板端告警 → SSH 事件与截图 → Windows
```

主摄识别车辆、估算距离与接近速度，并将车道标线映射到道路视图。副摄独立运行，默认识别行人。Windows 监看端接收危险事件和抓拍，支持本地记录、历史回看和 CSV 导出。

## 运行

安装 Python 3.10+ 和 Tk（Debian 上的 `python3-tk`）。先创建虚拟环境，再安装依赖。

```shell
python -m pip install -r adas_vision_pcie/requirements.txt
python -m unittest discover -s adas_vision_pcie -p "test_*.py"
```

在 RK 上使用有授权的 v0635b 板卡工程，运行其 DMA 采集服务。按需准备同一板卡包中的 `arm_isp.py`、与板卡匹配的 `rk_yolo_srv` 和 `yolov8n.rknn`。把 `arm_isp.py` 放在 `dual_console.py` 同目录，或通过 `PYTHONPATH` 加入它所在的目录。

```shell
python adas_vision_pcie/dual_console.py --fpga --screen-only --alert-port 8791 --yolo-helper /path/to/rk_yolo_srv --yolo-model /path/to/yolov8n.rknn
```

在 Windows 上配置到 RK 的 OpenSSH 密钥登录，先确认 SSH 可连，再运行监看端。按实际账号、主机名和密钥路径替换下例。

```powershell
python adas_vision_pcie/pc_alert_monitor.py --host linaro@rk3576.local --ssh-key "$env:USERPROFILE/.ssh/id_ed25519"
```

- [应用使用说明](adas_vision_pcie/README.md)
- [FPGA 与 RK 对接说明](adas_vision_pcie/PCIE_SETUP.md)
- [板卡与模型依赖](THIRD_PARTY.md)
