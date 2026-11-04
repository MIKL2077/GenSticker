# InsightFace InSwapper 与 GenSticker 的适配调研

调研日期：2026-10-30，Asia/Shanghai。服务器只读采样时间：17:35:51。状态：资料与代码审查、真实环境核验已完成；尚未运行 InSwapper 推理，性能、效果和并发容量均未实测。

结论：**InSwapper-128 可以作为真人表情模板的候选换脸引擎；现阶段不适合直接替换猫咪／卡通表情融合主线，也不宜直接加入现有 API 与 worker 常驻模型。** CPU 推理路径存在，但当前应用资源余量较紧，需要先做独立进程验证。正式产品还须核对换脸及配套识别模型的使用授权。

## 1. 当前开发进度

已读取关联聊天《了解进度并继续表情融合》（`01a182f3-f028-7ab3-ad4e-5c5a4fdcdd9b`）的近期工作与最终交付记录，并交叉检查当前文件、审核状态及线上健康接口。

- 实际开发仓库为外层项目的 `source/`，`app/` 为旧副本。当前分支 `codex/rebuild-meme-slots`，HEAD 为 `ed6dcfb`。仓库已有字符画、审核工具及测试的未提交改动，本次没有修改它们。
- 正式模板库 **967 / 1500**，尚差 **533**；本轮 Tenor 累计 24 项通过，其中 8 项已发布、16 项尚待发布。另有 14 项修订待复核、12 项否决、2 项暂缓。50 个有效候选与 2 个暂缓项、727 个可解码来源动画是不同口径，不能累加为已发布模板。
- 最新 14 项修订生成了 126 份三头像完整 GIF，修正跟随、嘴部、眨眼、视线和眉形；部分 GAN 方案仍失真而禁选。当前问题包括动作语义、眼镜与五官稳定性、跟踪和侧脸可见性，并非只有融合边缘。
- 现有实现是 MediaPipe 人脸定位／网格、逐模板离线位置与遮罩、几何驱动，以及固定哈希的 GANimation EmotionNet ONNX。动作曲线由人工标定，不是自动识别猫咪情绪；生产不依赖 PyTorch。
- 多图分享已改为最多 9 张动态 GIF 拼图，代码已提交；真实手机相册保存与好友接收仍待真机验收。
- 新模板继续逐项人工审核；已有自动制模发布入口已关闭，六小时素材采集仍保留。

项目依据：[Tenor 进度与验收记录](TENOR_FACE_REVIEW_2026-10-30.md)、[已发布表情驱动](SELECTED_EXPRESSION_DRIVERS_2026-10-29.md)、[README](../../README.md)。健康接口本次只读核验返回 `{"status":"ok","templates":967}`。

## 2. 开发环境与服务器实况

本机为 macOS ARM64、Apple M4、32 GiB 内存；Node.js 24.13.0，`source/.venv` 为 Python 3.12.14，ONNX Runtime 1.31.0、OpenCV 4.14.0.94、NumPy 2.3.5、Pillow 12.3.0。该环境没有安装 insightface 或 torch；旧的小模型实验有独立虚拟环境，不能与应用环境混为一谈。前端为 uni-app / Vue 3 / Vite，主要交付微信小程序；后端为 FastAPI / Pillow / Skia / SQLite 和独立队列 worker。

线上为 Linux x86_64（内核 6.8.0-124，glibc 2.39）、4 vCPU、Xeon Gold 6148 @ 2.40 GHz，物理内存约 15.61 GiB，无 swap；未发现 NVIDIA 设备，PCI 仅列虚拟显示设备。根盘约 99 GB，采样可用约 50 GB。两套应用虚拟环境均为 Python 3.12.3、ONNX Runtime 1.31.0、OpenCV 4.14.0.94、NumPy 2.5.4、Pillow 12.3.0，均无 insightface、onnxruntime-gpu、torch。

**硬件总量不是应用可用额度。** 实际 systemd 配额与采样值：

- `gensticker.slice`：合计 CPU 上限 200%（两个核的 CPU 时间），MemoryHigh 3 GiB、MemoryMax 4 GiB、TasksMax 192；采样 MemoryCurrent **2.616 GiB**，历史 MemoryPeak **2.944 GiB**。
- API：MemoryMax 2 GiB，MemoryCurrent **1.050 GiB**；worker：MemoryMax 2 GiB，MemoryCurrent **1.195 GiB**。两者均 active / running，异常重启计数 0；各自的 CPU 200% 仍受父 slice 合计 200% 约束。
- 父 slice 距 MemoryHigh 约 **0.384 GiB**、距 MemoryMax 约 **1.384 GiB**。MemoryHigh 是回收／节流阈值，MemoryMax 是硬上限；这些差值随负载变化，不能作为模型可占用空间承诺。MemoryCurrent 含被 cgroup 计入的缓存，不是单个 Python 进程 RSS。
- 整机采样 MemAvailable 约 10.82 GiB、负载 0.25 / 0.10 / 0.02，只能说明采样时主机较空闲，不能越过上述应用配额。同机还有其他业务。

模型加在 API 与 worker 两个进程会分别创建会话并消耗内存；不能假设只付一份模型内存。当前 release 链接仍指向既有 release 目录，部分运行文件已逐次更新，不能仅凭目录日期判断生产代码版本。

非敏感原始数值保存在[环境证据](INSWAPPER_ENVIRONMENT_2026-10-30.json)。本次没有重启服务、修改配额、安装服务器依赖或上传照片。

## 3. 模型本身需要什么

本报告评估公开的 **`inswapper_128.onnx`**，不将商业 API、手机模型或其他高分辨率产品的宣传能力算到它身上。官方仓库审查时 master 为 `c6c3af7bd2d0a0bf4b78c78437357f3521aa5d52`。

### 输入与输出

InSwapper 做身份迁移：source 是用户照片，target 是承载动作的目标脸。它对目标脸进行五点对齐，再结合 source 的身份 embedding 生成换脸结果。官方示例要求使用 **buffalo_l 配套 ArcFace** 的 embedding；当前 MediaPipe 点位、FERPlus 情绪概率或 GANimation 的 17 个 AU 不能代替这个 embedding。不能未经验证改用更小识别模型。

官方说明的脸部输入与输出为 **128 × 128**；贴回后整图尺寸可保持原样，但插值放大不等于恢复高清五官。它没有 AU、独立视线、眼睑或嘴形控制输入。目标表情与姿态的保留程度是效果验证项，而非逐帧精确保证。[官方模型说明](https://github.com/deepinsight/insightface/blob/c6c3af7bd2d0a0bf4b78c78437357f3521aa5d52/examples/in_swapper/README.md)、[官方推理实现](https://github.com/deepinsight/insightface/blob/c6c3af7bd2d0a0bf4b78c78437357f3521aa5d52/python-package/insightface/model_zoo/inswapper.py)。

### 权重、依赖与运行方式

官方 GitHub `model-zoo` release 元数据本次返回：

- `inswapper_128.onnx`：**554,253,681 bytes / 528.58 MiB**；release 声明 SHA256 为 `e4a3f08c753cb72d04e10aa0f7dbe3deebbf39567d4ead6dce08e98aa49e16af`。
- `buffalo_l.zip`：**288,621,354 bytes / 275.25 MiB**；release 声明 SHA256 为 `80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f`。

以上是在线发布元数据，不是本次下载后计算的文件校验。压缩包大小也不是解压大小或 RSS。InSwapper 单文件约为现有 33,924,122-byte EmotionNet ONNX 的 **16.34 倍**，不能由文件比值推断推理速度。

可通过 ONNX Runtime CPU 路径执行，不要求 CUDA，也不要求部署 PyTorch 或重新训练模型。但需补齐对应检测／对齐与身份编码链路，并核验本机 ARM 与服务器 x86_64 的实际兼容性。当前上游 Python 文档为 2.1，支持 Python 3.10+；普通安装不再默认编译可选 face3d 扩展，不能照搬旧 0.7.x 教程认定必须安装 C++ / Cython。建议在独立环境锁定已验证版本，不对生产直接执行 `pip install -U`。[当前 Python 包文档](https://github.com/deepinsight/insightface/blob/c6c3af7bd2d0a0bf4b78c78437357f3521aa5d52/python-package/README.md)、[官方 release](https://github.com/deepinsight/insightface/releases/tag/model-zoo)。

只需使用检测、识别和换脸功能。不要同时加载不需要的年龄、性别、三维点位或 GUI；旧格式模型包的 `allowed_modules` 过滤发生在创建模型之后，仍应观察冷启动峰值。官方包装器读取 ONNX 图中的 embedding 映射并建立 ORT 会话，也会有额外临时内存，不能将权重大小视为完整预算。[FaceAnalysis 加载实现](https://github.com/deepinsight/insightface/blob/c6c3af7bd2d0a0bf4b78c78437357f3521aa5d52/python-package/insightface/app/face_analysis.py)。

服务器首先测试 FP32 CPU 基线。FP16 文件变小不代表该 Xeon 上更快，CPU 算子支持和转换开销需要实测；INT8 也需重新验证画质与兼容性。不要预先加入 GFPGAN / CodeFormer；它们是额外模型，无法保证既有身份、表情和资源预算。[ORT 精度转换说明](https://onnxruntime.ai/docs/performance/model-optimizations/float16.html)。

## 4. 与当前功能逐项匹配

**真人目标脸：值得做对照。** 模板原来就是清楚的人脸，且表情主要来自目标人物时，身份替换比单纯拉伸上传照片更符合任务形式，可能改善皮肤融合和身份观感。这是基于输入形式的适配判断，尚无本项目 InSwapper 成品支持“必然更好”。正面／轻微侧转应先测；大侧脸、遮挡、眼镜、舌头及大幅张嘴仍需逐项审核。

**猫咪、柴犬、卡通：不作为直接替换方案。** 官方公开链路针对人脸，未提供动物表情到人脸的迁移保证。当前猫脸坐标、去五官底图与语义定位可以指导原有合成，却不能使猫脸变成有效的人脸目标。手工填五点可能绕过“检测为空”，不能补齐动物与人的结构差异或训练分布。此处是不具备可靠支持证据，不是已经实测所有动物输入都失败。

**动作跟随与眼神：仍需现有制作层。** InSwapper 不替代 GIF 时间轴、逐帧脸区、遮挡、嘴部范围或跟踪插值，也不能接收当前 `gaze_x` / AU 曲线直接控制“鄙视眼神”。GANimation 后再 InSwapper 可能成为实验组合，但增加重绘与开销；source=用户、target=同一用户静态照片也不会凭空产生猫咪动作。

**保留场景：可以复用合成器，不能直接照搬默认 paste-back。** 使用 `paste_back=False` 获取脸块与变换，再进入现有支持区、保护区和道具遮挡合成路径更可控。编码前检查保护区、原文字、耳朵、手、身体及逐帧时长；官方平滑脸部融合蒙版本身不提供本项目的保护区契约。新方案需独立 method / 版本和审核样张，不能覆盖已通过配方。

**前端：宜继续服务器队列生成。** 小程序已有服务器回退路径，第一阶段不需要把数百 MiB 权重塞进小程序；可保持用户制作流程，后端按模板能力选引擎。前端动态拼图与这个模型的采用没有直接依赖。

## 5. 服务器能不能承担

**可做小批离线验证，尚不能判定适合现有在线常驻。** 528.58 MiB 换脸文件已经大于当前父 slice 距软阈值的差值，还需配套识别模型、ORT 中间张量和现有人像／编码链路。文件大小与 RSS 不等价，因此这说明风险和测试必要性，不是已测得必然 OOM。整机 16 GB 与空闲较多也不能证明 2 GiB worker 装得下整条链路。

当前 50 个有效候选实际含 3–40 个配方帧，中位数 24 帧。InSwapper 通常按不同目标脸帧推理；相邻帧像素变化时，现有“相同 AU 动作复用”不再等价于可复用换脸结果。9 张各 24 个不同目标帧的示例会需要最多 216 次换脸前向，尚未计算检测、身份编码、合成与 GIF 编码；这是工作量示例，不是当前九图任务的实测值。

可复用：同次任务内用户身份 embedding、离线审核过的目标五点、相同目标裁剪帧。去重缓存应包含目标图像／裁剪、对齐参数、源身份、模型和预处理版本；不能只按“同一表情”复用。源身份特征随私有任务生命周期释放，不新增长期身份库。

端到端耗时应分别测量：冷加载、照片定位与身份编码、所有不同目标帧的推理、保护区合成、GIF 编码、排队及结果存储。不能用之前 EmotionNet 的约 0.3 秒局部实验或 633.5 MiB 整链实验替代 InSwapper 数据，也不能套用别人的 GPU FPS。

在当前共享机器验证时，独立进程先限制 CPU 100%、单任务串行、ORT intra/inter-op=1、顺序执行并关闭空转；这些是**建议的实验设置**。独立进程不代表资源免费：须核对父 cgroup 是否仍在 4 GiB 内，并给整机其他业务留预算，不能通过换 slice 绕过现有约束。先测冷加载峰值，若超过可分配预算便转到独立测试机，而非自动提高生产上限。[ORT 线程配置](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)。

## 6. 授权与维护边界

官方区分 MIT 代码与预训练权重：模型默认仅限非商业研究，公开下载不等于获得产品部署权。官方分别列出了 InSwapper 与 buffalo_l 等识别模型的授权联系途径；应向供应方明确换脸、配套识别／检测模型、服务器部署及结果使用的覆盖范围。当前没有核实本项目持有这些权利，官方公开页面也未给出可用于本项目预算的固定授权价格。本次没有联系供应商或购买许可。[官方许可声明](https://github.com/deepinsight/insightface#license)、[换脸商业许可](https://www.insightface.ai/solutions/face-swapping)。

另外，公开 InSwapper 示例 README 明确表示该模型与 demo 不再维护，InsightFace Python 包仍更新不代表这一换脸模型持续更新。现有 GANimation 权重商业权利也尚未独立核实，继续使用它不消除这项既有问题，详见[当前模型记录](../../deploy/model-licenses/MODELS.md)。

## 7. 建议的下一阶段验证

1. 本机独立环境使用官方来源权重，核验下载内容 SHA256、实际输入输出、CPU provider 与 source embedding 兼容性，锁定依赖；不改应用虚拟环境。权重不入 Git。
2. 先选 6 个有代表性的真人模板，覆盖静态、眨眼、张嘴、眼镜、轻微侧转和遮挡；使用既有获准头像并提供完整 GIF 对照。另选 2 个动物／卡通模板作适配边界探针，失败如实记录，不计为可用模板。此处是待执行方案。
3. 并列当前方案与 InSwapper；检查像不像本人、表情语义、眼镜／牙齿、帧间闪烁、跟随、遮挡，以及保护区、文字、尺寸、完整时序与循环。身份相似分数只能辅助，尤其同一 ArcFace 既生成又评分时不能当独立质量证明。
4. 画质有收益后再做 Linux 限额实验：冷／热启动分开，记录 peak RSS / cgroup MemoryPeak、单帧与整 GIF 耗时、中位与尾部、失败率及基线服务健康。先单任务，再按实测决定是否测试九图排队，避免共享机器满载压测。
5. 仅在真人分支收益明确、授权覆盖且端到端预算通过后，才增加可选引擎、固定模型校验、超时／取消、缓存和失败回退。缺脸或推理失败应明确回退，不能计作模型成功。模板逐项复审后再考虑发布。

本次交付仅新增本调研及环境证据；没有下载大型权重、生成 InSwapper 样张、修改运行时代码、部署、提交或推送。
