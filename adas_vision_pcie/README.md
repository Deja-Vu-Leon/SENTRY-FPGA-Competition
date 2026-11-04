# SENTRY：YOLO 多目标防碰撞研究项目

界面已按较小屏幕重新布局：中央视频会随窗口缩放；右侧参数分为“天气 / 阈值 / ROI”三个页签，点击页签即可查看对应滑块；左侧功能区有独立滚动条。直方图可在左侧关闭以腾出视频显示空间。窗口最小尺寸为 1040×620；缩小窗口时，所有功能仍可通过页签或滚动条访问。

视频中的绿色线标出检测到的左右车道边界；两条线都有效时，以半透明青色标出估计的当前车道，并以蓝色标出右侧相邻车道的几何延伸。偶发漏检时最多保持上一车道 6 帧，界面标为“短时估计”；连续漏检后清除着色。**实时场景摘要放在右侧“参数调整”上方，不遮挡视频**，显示当前帧的车辆数量、最高风险、车道状态和最近车辆距离。视频右侧新增随车道偏移和车辆位置更新的透视道路示意图，方块表示已跟踪车辆。该图是 **2.5D 示意视图**，车辆纵深依据单目估算距离布置，不是三维场景重建，也不控制车辆。当前 Hough 车道线算法只提供直线近似；弯道、磨损线、积雪或遮挡下可能失效。若需达到参考图那种逐像素道路分割，应另外训练并接入车道/可行驶区域分割模型，在目标视频上验证。

独立于上一项目的新项目。视频路径：**摄像头 → 安路 FPGA → PCIe → RK3576 驱动/V4L2 → YOLO RKNN → 多目标跟踪与车道分析 → UI**。框选 `car`、`bus`、`truck`、`bike`（COCO bicycle）和 `motorbike`（COCO motorcycle），显示距离、速度、碰撞风险；同时提取车道线，显示车道偏离警告和车道保持方向提示。[Rockchip 官方 YOLOv8 示例](https://github.com/airockchip/rknn_model_zoo/tree/main/examples/yolov8)列出 RK3576，并提供优化 ONNX 与 RKNN 转换流程。

## 快速运行

建议 Python 3.10–3.12 的桌面演示环境；Windows Python 3.13 需确保依赖有对应安装包：

```bash
python -m venv .venv
# Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

**在 PC 上用自己的视频实际验证**，安装 PC YOLO 依赖，然后运行：

```bash
pip install -r requirements-pc.txt
python app.py --video /path/to/your-video.mp4 --pc-model yolov8n.pt \
  --ego-kmh 40 --focal-px 900 --reaction-s 1.5 --decel-mps2 4
```

Windows PowerShell 可把命令写成一行：`python app.py --video "D:\video\road.mp4" --pc-model yolov8n.pt`。首次使用 `yolov8n.pt` 时，Ultralytics 需要网络下载权重；离线时可提前把权重保存到本地并把 `--pc-model` 指向文件。也可先运行 `python app.py`，在界面中先“加载 PC YOLO 模型”，再点击“本地视频”。[Ultralytics 的安装和推理接口](https://docs.ultralytics.com/quickstart)、[结果框 API](https://docs.ultralytics.com/modes/predict)是该 PC 后端的依据。

使用你提供的行车记录仪视频时，在项目目录运行：

```powershell
python app.py --video "C:/media/drive.mp4" --pc-model yolov8n.pt
```

### 直方图、显示滑块与危险日志

- 左侧“显示 RGB 直方图”控制视频下方的三色亮度分布图。直方图来自当前展示的底图（叠加检测框之前）。
- 右侧“显示比例：原图 0 / 增强 100”滑块只改变**预览画面**的原图/天气增强图混合比例；开启天气增强时，YOLO 与车道分析始终使用增强帧。调到 0 可对照原画，调到 100 显示完整增强效果。天气增强关闭时，预览保持原画。
- 左侧“保存危险画面日志”默认启用。**真实视频**出现高碰撞风险或车道偏离时，把带检测框和车道标注的 JPG 截图保存在项目 `logs/`，并向 `events.jsonl` 追加时间、来源、目标类别与距离、车道状态和图片文件名。演示场景不会写危险截图；同类危险连续出现时至少间隔 3 秒再保存。左侧按钮可打开日志目录。
- 默认仅保留最多 512 MiB 的危险截图，超限时删除最旧的 `danger_*.jpg`；文字事件历史保留，较早记录中的图片可能已被清理。可用 `--log-dir /path/to/logs --log-max-mb 512` 修改位置和上限。日志是**本地保存**，未配置网络上传。请在实际设备上留意磁盘空间和视频隐私。

### 极端天气画面增强

左侧勾选“极端天气画面增强”，右侧选择“雾霾 / 沙尘暴 / 暴风雪”并调整强度。**默认关闭**，关闭时识别和车道分析沿用原始输入帧；开启后，增强帧会送入原有 YOLO 识别、跟踪和车道分析，检测类别与后处理逻辑不变。切换模式或强度时会重置短期跟踪状态，避免跨两种画面直接计算速度。也可在启动时指定：

```powershell
python app.py --video "C:/media/drive.mp4" --pc-model yolov8n.pt --weather-on --weather-mode 雾霾 --weather-strength 50
```

`weather.py` 的雾霾模式采用近似暗通道透射率恢复并增强局部对比度；沙尘暴模式补偿色偏后增强对比度；暴风雪模式增强局部对比度。强度 0 保持原帧不变。它们是**图像增强**，无法恢复被沙尘、雪或浓雾完全遮挡的物体；增强过强可能放大噪声、改变颜色，甚至降低 YOLO 与车道检测准确率。应同时保存原图与增强图，在实际天气数据上分别统计漏检、误检和帧率。雾霾模式在本机 960×540 帧上的预处理约为 23 ms/帧（首次调用更慢）；RK3576 上未测，启用后很可能降低整机帧率。

车道线功能可独立于 YOLO 使用：即使 PC 模型权重尚未下载，直接 `python app.py --video "视频路径"` 仍可检查车道提取与偏离提示。

### Windows 安装出现 SSL EOF

若 `pip install` 显示 `SSLEOFError`、`Could not fetch URL https://pypi.org/simple/...`，随后出现 `No matching distribution found`，先按网络连接问题处理；后一句并不证明包不存在。可在项目目录的 PowerShell 中临时改用[清华 PyPI 镜像](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)：

```powershell
python -m pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple -r requirements-pc.txt
python -c "import ultralytics, torch; print('YOLO and PyTorch ready')"
```

无需先升级 pip。若镜像也报 SSL EOF，检查浏览器是否能访问该镜像、公司/校园代理、VPN 和安全软件的 HTTPS 设置；换一个可用网络后再试。不要用 `--trusted-host` 或关闭证书验证来掩盖连接故障。模型权重 `yolov8n.pt` 的首次下载还需要能连接 Ultralytics 的权重下载地址；可在可联网设备上获取权重后复制到本机，再把完整文件路径传给 `--pc-model`。

演示模式的目标框、距离与速度均为模拟值。读取真实视频但不加载模型时，不会显示伪造识别结果。视频结束后会停在结束提示，不会自动切成演示画面。目标速度计算使用视频帧时间戳；若视频文件没有有效时间戳，回退为帧号/标称帧率。**对录播视频，`--ego-kmh` 应填拍摄时的自车速度**；未知时速度与预警距离只能作示意。板端使用前需安装匹配 RK3576 固件的 `rknn-toolkit-lite2` 和 RKNPU2 runtime，安装 OpenCV、Pillow、numpy；板厂 OpenCV 包可能比通用 wheel 更合适。

板端首先检查 FPGA PCIe 驱动是否输出标准视频节点：

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
python app.py --pcie-device /dev/video0
```

若 FPGA 输出私有 DMA 包或 JPEG/LZ77 压缩数据，必须先由驱动/解码层变为 V4L2 可读取的视频帧；本项目不含 PCIe 驱动。PC `.pt` 模型与板端 `.rknn` 是不同后端，PC 验证结果不能代替 RKNN 转换后的板端验收。

## RKNN 模型准备

在与工具链匹配的 x86 Linux 开发环境中，按 [官方转换说明](https://github.com/airockchip/rknn_model_zoo/tree/main/examples/yolov8)下载优化的 `yolov8n.onnx`：

```bash
git clone https://github.com/airockchip/rknn_model_zoo.git
cd rknn_model_zoo/examples/yolov8/model
./download_model.sh
cd ../python
python convert.py ../model/yolov8n.onnx rk3576 i8 ../model/yolov8n_rk3576.rknn
```

官方转换脚本默认用 COCO 子集做 INT8 校准。正式部署应使用 FPGA **最终输出帧**制作代表性校准列表并修改脚本中的 `DATASET_PATH`，然后重转。先在板端运行官方示例验证模型，再运行：

```bash
python app.py --pcie-device /dev/video0 --model /path/to/yolov8n_rk3576.rknn \
  --ego-kmh 40 --focal-px 900 --reaction-s 1.5 --decel-mps2 4
```

本项目解码器要求官方优化 YOLOv8 的 9 个输出张量和 COCO 80 类顺序。普通 YOLO 导出或更改类别数的自训模型不能直接替换。官方类别包含 bicycle、car、motorbike、bus、truck；界面用用户要求的 `bike` / `motorbike` 名称展示。[官方后处理与类别列表](https://github.com/airockchip/rknn_model_zoo/blob/main/examples/yolov8/python/yolov8.py)

## 估算公式与适用边界

### 车道线与车道保持提示

`lane.py` 对画面下半部的白色/黄色标线做颜色筛选、Canny 边缘与 Hough 线段拟合，绘出左右车道边界。以图像中心作为相机安装位置的**临时假设**，计算相机相对于车道中心的偏移量：`(图像中心 − 车道中心) / 车道宽度`。偏移比例超过 0.22 且连续 3 帧成立时，显示“偏左”或“偏右”；超过 0.08 时给出轻微向相反方向修正的提示。若只找到一侧线或车道宽度不可信，显示“车道不可用”，不会触发偏离警告。界面左侧可以关闭车道分析。

界面右侧的“车道图像调参”提供实时滑块，无需重启视频：

| 控件 | 作用 |
|---|---|
| 白线亮度阈值 | 白色标线 HSV 亮度下限；调高可减少亮背景，过高会漏掉暗处标线。黄色标线仍由固定的颜色范围提取。 |
| 边缘低/高阈值 | Canny 边缘检测的滞后阈值；高阈值会自动保持大于低阈值。 |
| ROI 顶部高度、顶部半宽、底部半宽 | 调整梯形道路检测区域；蓝色轮廓显示当前 ROI。顶部高度是画面高度百分比。 |
| 直线投票阈值、最短线段 | 控制 Hough 直线筛选；前者越高、后者越长，通常越严格。 |
| 偏离阈值 | 车道中心偏移比例超过该值且连续 3 帧成立时触发偏离警告。 |

预览菜单可选“原图”“二值图”“边缘图”。二值/边缘图显示 ROI 内的中间结果和拟合线，便于定位漏检原因；切回“原图”查看车辆框与车道叠加。“恢复默认”重置全部滑块。建议先调 ROI，再看二值图调亮度阈值，最后看边缘图调 Canny 与 Hough。所有参数为当前运行会话设置，重启后恢复默认。

**车道保持辅助目前仅为视觉提示，没有方向盘控制、转向力矩输出或执行器接口。** 相机不居中、弯道、变道、道路施工、阴影、积水、磨损标线、邻道标线与夜间灯光都可能造成误判。实际部署前要标定相机中心并用完整视频逐帧评估；可将当前传统视觉模块替换为经训练和验证的车道模型。

- **距离**：`焦距像素 × 假定目标宽度 / 目标框像素宽度`。默认宽度 car 1.8 m、bus/truck 2.5 m、bike 0.6 m、motorbike 0.8 m。这些只是类别平均占位值；斜向车辆、遮挡、截断框和车型差异会产生明显误差。焦距必须用实际镜头标定。
- **目标速度**：同一目标连续帧的距离变化给出视线方向的接近速度；再以用户输入的自车速度推算目标的近似速度幅值。单摄像头无法可靠区分目标行驶方向或分离真实三维运动，自车速度若未接入 CAN/GNSS 而由人工填写，显示值不能当作实测车速。横向运动、检测框抖动和跟踪错配尤其会影响结果。新目标先显示 `--`。
- **识别框稳定化**：YOLO 的候选框阈值为 0.25；新目标仍需至少 0.35 的置信度且连续匹配两帧才显示。已确认目标的框使用指数平滑；短暂漏检最多保留 6 帧且不超过 0.35 秒。暂失时画灰色细框并标记 `TRACKING`，不更新速度、最近距离或碰撞风险；重新检出后沿用目标编号。类别偶发跳变时优先保留已有类别，连续证据足够才切换。此机制减少闪烁，但可能造成短时残影，也不能修复持续漏检或模型误检。
- **反应时间**：`--reaction-s` 是可设置的驾驶员反应时间假设，默认 1.5 秒，不是自动测出的人的反应时间。
- **预警距离**：`接近速度 × 反应时间 + 接近速度² / (2 × 假定减速度) + 3 米余量`。低于此距离显示高风险，低于 1.5 倍显示中风险，其余显示低风险。只有连续跟踪后才给风险等级。

这是一套**研究与联调界面，不能用于实车自动制动或安全决策**。尚未验证 RK3576 性能、FPGA PCIe 链路、<300 ms 延迟、全天候识别精度、单目测距/测速误差或报警误报率。实际安全系统应接入经过标定的相机、自车速度信号，使用多传感器冗余、严格验证和失效保护。

## 文件

- `app.py`：界面、视频输入及框选显示。
- `vision.py`：官方布局的 RKNN YOLOv8 检测适配器。
- `tracker.py`：多目标关联、距离/速度与风险估算。
- `lane.py`：车道线提取、偏离判定与方向提示。
- `weather.py`：可选的雾霾、沙尘暴与暴风雪图像增强。
- `requirements.txt`：桌面依赖。
- `requirements-pc.txt`：PC YOLO 推理依赖。

## RK3576 双路视觉工作台

在 `adas_vision_pcie` 目录运行 `dual_console.py`。需要 Python 3.10+、
Tk、OpenCV、NumPy 和 Pillow，可使用本目录的 `requirements.txt`。
Debian 的 Tk 模块由系统包 `python3-tk` 提供。界面需在图形桌面会话中启动。
界面使用 [TypeUI Professional](https://github.com/bergside/awesome-design-skills/tree/main/skills/professional)
的浅色面板、黄色主操作和紧凑间距，指标数字采用本机等宽字体。

### FPGA 实时双路

先按 [PCIe 联调说明](PCIE_SETUP.md) 在 RK 上启动同版 `cs500_live.py`，
并用 `rk_dual_camera_test.py` 检查两路端点都有新帧。然后运行：

```bash
python3 dual_console.py --fpga
```

工作台从同一个采集服务读取主摄 `/frame?cam=0`（J2 IMX415）与
副摄 `/frame?cam=1`（J3 CS500）。两路独立处理和刷新。
J2 实时输入在处理前做上下翻转，以校正当前相机安装方向。
拍摄显示屏时，在每路点“标定屏幕”查看实时原图。点击左上内角后画面冻结，
接着点右上、右下、左下内角。需要重来时点“重新取帧”恢复实时预览，
再点“应用标定”。选区保存到 `screen-roi.json`，之后去雾、车辆或行人识别只使用
透视校正后的屏幕区域。移动相机或屏幕后需重新标定。启动时加 `--screen-only`，
未标定通道只预览。也可用 `--main-screen` 和 `--aux-screen` 按上述顺序传入八个归一化坐标。

车辆框显示距离与相对速度，正值为接近，负值为远离。速度只根据连续 NPU 测距
估算，光流帧更新框位置并沿用最近的读数；趋势不稳时显示 `--`。
“车速参考”可填入片源中本车的速度，用于估算同向车辆车速（显示 `~… km/h`）；
留空即恢复相对速度，也可用 `--ego-kmh` 启动时指定参考值。

右上角预警与视频和 3D 视图共用风险结果。绿色为正常，黄色为接近时间不足 4 秒
或按本车参考车速算出的前向跟车时距过短，红色为连续测得距离过近或预计 2.2 秒内
接触。速度触发限于画面前进方向附近。过近距离默认 10 m，可用 `--near-alert-m` 调整。
副摄默认识别人，开启“副摄后视”后才参与后向车辆预警。
车速、距离和接近时间为单目演示估算；拍摄 HDMI 回放时，它们描述的是视频画面里的目标。
信号恢复后可点击“连接双路 FPGA”重新取流。服务不在默认地址时使用
`--endpoint http://地址:端口`。

板上可复用同一 FPGA 工程的原生 `rk_yolo_srv` 和 RK3576 YOLOv8n RKNN 模型，
为两路分别启动 NPU 推理。启动时加入 `--yolo-helper ./rk_yolo_srv --yolo-model ./yolov8n.rknn`。
FPGA 实时画面只添加目标框。主摄检测车辆，支持雾霾和沙尘暴增强；副摄默认检测行人。
如果在 RK 打开没有画线的本地录播，可手动勾选“录播画车道线”。

### PC 预标线并经 HDMI 播放

在 PC 安装 PyAV 后，可用 `render_lane_clip.py 源视频.mp4 输出.mp4` 离线导出
H.264 视频。默认 `lane_clip_guides.json` 对应高速素材前 12 秒，左右车道线已按
关键帧校准；换素材时用 `--guides` 指定对应的坐标文件。导出只画线，不调用车辆模型。
将导出的 MP4 在主摄所拍的 HDMI 屏幕上全屏循环，实时工作台会从该画面识别车辆并添加框。
RK 同时从主摄校正画面识别源视频中的亮绿色窄标线，将可见的左右标线投到 3D 行车视图。
该视图会分别显示双侧、仅左侧、仅右侧或未检出，标线离开画面后短时内清除。
两路框和计数使用各自的当帧结果。录播与混合输入使用独立预览。

### Windows 双路录播

从项目的 `adas_vision_pcie` 目录，在 PowerShell 执行：

```powershell
$media = 'C:/media'
$a = Get-ChildItem -LiteralPath (Join-Path $media '真实的高速公路团雾') -Filter *.mp4 -File | Select-Object -First 1
$b = Get-ChildItem -LiteralPath (Join-Path $media '行车记录仪') -Filter *.mp4 -File | Select-Object -First 1
python dual_console.py --media-dir $media --video-a $a.FullName --video-b $b.FullName
```

每个通道也可通过“打开录播”切换文件。录播各按自己的标称帧率播放，到片尾停止。
拷到 RK 后可把同样的参数指向板上的文件路径。
工作台默认全屏，视频按原宽高比适配窗口。按 F11 切换全屏，按 Esc 返回窗口，
也可加 `--windowed` 直接以窗口模式启动。左侧上方为主摄，下方为副摄，
右侧显示最近 20 秒的处理帧率、RKNN 推理耗时、车辆和行人数量，
并在曲线旁显示基于主摄双侧车道线估计的行驶路径。

主摄雾霾模式采用暗通道去雾和局部对比度增强，沙尘暴模式先补偿色偏再去雾。
车辆模型使用增强后、叠加前的画面。车道线先用颜色、边缘和 Hough 提取候选，
再用一致线段、Huber 拟合和道路几何筛选。连续三帧确认后才显示稳定边界。
双侧确认时显示绿色车道区域。单侧和最多两帧的短时保持用虚线表示。
拟合支持度衡量支持线段的纵向覆盖范围，单侧结果按一半计。
天气模式选“关闭”或强度调到 0 可旁路，滤波和车道线分别可关闭。“查看原图”切换两个预览，
参数仍继续生效。处理默认将输入缩到宽度不超过 960 像素，支持用 `--width` 调整。
可用 `--main-width 480` 单独降低主摄处理宽度。主摄实时取帧、解码和天气增强与
车道线及目标处理并行执行，两阶段之间只保留最新的待处理帧。主摄默认每 3 帧、副摄每 2 帧运行
一次 NPU 检测。间隔帧用 OpenCV 稀疏光流拟合当帧目标框，标注为 `TRK`。跟踪失效、
场景突变或关键帧超过 400 ms 时会提前重新检测。两个间隔可用
`--main-detect-every` 和 `--aux-detect-every` 调整，设为 1 可逐帧推理。

处理 FPS 是各路处理吞吐。单帧处理耗时包括
RK 侧缩放、算法、推理或跟踪以及画框。
RKNN 推理耗时来自原生推理程序，覆盖输入设置、运行及输出获取。
推理趋势直接采样各路实际运行 NPU 的帧。推理间隔以内沿用最近实测值连接曲线，
超过 1.5 秒没有新样本时断开。
单帧处理耗时不能直接当作整链路端到端延迟。
车道线为可视化估计，适用于素材验证和板卡联调。

右侧 3D 行车视图用主摄的车道与车辆检测绘制自车、前方路径和目标线框。
RGB 直方图可选择主摄或副摄，统计叠加目标框之前的画面。
“图像调参”可分别启用各通道的 RK ARM ISP，调色彩预设、白平衡、伽马、亮度、
对比度、降噪和锐化，也可调检测置信度下限及目标框线宽。
副摄面向后方时，勾选“副摄后视”或用 `--aux-rear` 启动，后向车辆也会参与距离估算。
界面里的约数按车型参考宽度、目标框像素宽度和有效焦距估算纵向距离。
`--front-focal` 和 `--rear-focal` 分别取各通道有效焦距像素数除以实际识别画面宽度。
默认使用 0.9，仅供演示。HDMI 翻拍时参数对应原始视频的有效成像比例和当前裁切。
过小或被画面边缘截断的目标不显示距离。3D 画面是透视示意，
距离与横向位置受车型、镜头、安装和框选误差影响。

### Windows 危险事件监看

打开桌面的「SENTRY 危险事件监看」，或从项目根目录运行：

```powershell
python adas_vision_pcie/pc_alert_monitor.py --host linaro@rk3576.local --ssh-key ~/.ssh/id_ed25519
```

RK 的双路程序带 `--alert-port 8791` 运行时，PC 通过 SSH 接收高风险事件日志和对应的危险抓拍，
不请求实时视频。抓拍 JPEG 和 JSON 日志保存在桌面的「SENTRY 危险事件日志」，可回看并导出 CSV。
