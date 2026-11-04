# 板卡与模型依赖

| 依赖 | 获取与用途 |
| --- | --- |
| 安路 FPGA / 米联客 AFH03 配套工程 | 从赛事或板卡供应商取得。需要 v0635b 位流、与 RK 内核匹配的 PCIe DMA 驱动，以及板端采集和 ARM ISP 工具。 |
| RKNN Runtime 与 RKNN Model Zoo | 从 [Rockchip 上游](https://github.com/airockchip/rknn_model_zoo/tree/main/examples/yolov8) 获取 RK3576 转换说明，安装与目标板匹配的运行库。 |
| Ultralytics YOLO | PC 的可选检测方式依赖 Ultralytics。包与模型按 [上游授权](https://www.ultralytics.com/license) 获取和使用。 |
| Python 运行库 | OpenCV、NumPy、Pillow、PyAV 和可选 Ultralytics 由软件包管理器安装。 |

供应商 IP、位流、驱动二进制、模型权重和演示视频各自沿用其原始授权。公开仓库提供 SENTRY 应用层及集成说明。
