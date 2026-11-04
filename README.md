# SENTRY · FPGA 比赛

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
