# 小模型表情融合实测（2026-10-28）

当前阶段是离线方案评估。尚未批准替换生产算法、部署候选模型或推送上一轮未批准的模板改动。

## 进度与范围

实际开发目录为外层项目的 `source/`；`app/` 为旧副本。当前分支为 `codex/rebuild-meme-slots`，本轮开始时已有三个未推送提交及尚未批准的模板、五官部件实验改动，均保留。

已读回上一聊天的完整评审背景：483 个带图模板中，282 个可用、118 个需调整、83 个不需要。此次选取其中 20 个需调整模板，覆盖真人、卡通、动物、眨眼、张嘴、道具和侧脸；使用 S03、S17、S29 三张既有私有测试照片。

本机生成 246 份实际成品：60 份原效果、60 份轻微几何形变、60 份 GANimation EmotionNet、60 份 GANimation CelebA，以及两张侧脸模板的 6 份 3DDFA 辅助投影结果。S03 原效果逐字节复制自原评估页；其他照片使用同一模板快照配方。

候选采用同一套离线区域和合成路径，不借用模板五官像素。与旧效果的差别同时包含区域、合成方式变化，因此不把它解释成单一模型变量的画质排名。动作参数由人工逐模板编写，未实现独立视线控制。正面照片无法补齐未拍到的侧面纹理。

## 已验证的结果

246 份成品尺寸和帧数正确，动画总时长保持一致。候选在 GIF 编码前的固定区域最大像素误差为零；GIF 调色板编码之后未声称逐像素不变。

6 份 3DDFA 投影出现网格翻转，已在评估页禁用选择并保留诊断图。其余 180 份候选未检测到网格翻转，但尚未得到用户画质批准。

实际图像显示：GANimation 可产生闭眼、张嘴及笑容，但部分结果出现眼球纹理异常、眼镜变形、嘴部伪影。轻微几何方案改动较温和，仍不能生成真实的新牙齿、舌头和侧脸。模板对齐、脸部覆盖及吸管遮挡仍有需要人工复核的个案。编码成功、资源合格均不等于效果可用。

## Linux 服务器资源验证

主机为 4 vCPU、16 GB、无 GPU。所有 186 份候选均在独立临时 systemd 进程内完成；每次仅一个方法，CPUQuota=100%、MemoryMax=768 MiB、MemorySwapMax=0、RuntimeMaxSec=120。没有加载进 API 或 worker。

- 轻微几何：60 份，进程峰值 126.5 MiB，整模板渲染中位数 144.3 ms，最大 2125.0 ms。
- GANimation EmotionNet：60 份，峰值 233.3 MiB，中位数 312.2 ms，最大 5533.6 ms。
- GANimation CelebA：60 份，峰值 233.4 MiB，中位数 313.5 ms，最大 5656.2 ms。
- 3DDFA 辅助：6 份，峰值 133.0 MiB；全部未通过上述网格检查。

渲染耗时包含推理和合成，排除照片检测/分割、冷加载、GIF 编码、上传及排队；同批次缓存重复动作。GIF 编码在个案中另行记录，最大约 725 ms；GAN 冷加载约 120 ms。不能将这些数据当作生产端到端延迟或并发容量。

测试前后 API/worker 的 PID、重启次数和健康状态一致，健康接口返回 959 个模板。临时服务器照片、模型和输出已清理。首次批量结果回传失败，后改为每种方法完成后立即持久化小报告，重新完成测量。页面展示本机效果图及服务器同参数流程的资源测量，未声称跨平台逐像素一致。

## 环境、产物与复现入口

本机运行于 macOS ARM64、Python 3.12、Node.js 24.13.0。候选依赖放在独立 `fusion-smallmodels-20261028/venv`；PyTorch 2.6.0 只用于离线导出，实际推理由单线程 ONNX Runtime CPU 执行。两组 GAN 生成器均为 8,467,584 参数；3DDFA MobileNet .5 的参数量为 850,398。导出与 PyTorch 的最大绝对误差小于 0.000005；权重与导出文件哈希记录在私有实验目录。

实验目录位于外层项目的 `fusion-smallmodels-20261028/`。保留了 `prepare.py`、`export_models.py`、`evaluate.py`、`baseline.py`、`server_benchmark.py`、`provenance.json`、`summary.json`、逐方法服务器报告和 `gallery/`。这些私有照片、模型及生成图不加入 GitHub。

仓库提供可复用的 `tools/qa/build_smallmodel_review.py`、`serve_smallmodel_review.py` 和 `smallmodel_review.html`。在 `source/` 中可执行：

```sh
.venv/bin/python tools/qa/build_smallmodel_review.py --lab ../fusion-smallmodels-20261028
.venv/bin/python tools/qa/serve_smallmodel_review.py \
  --directory ../fusion-smallmodels-20261028/gallery \
  --review-file ../fusion-smallmodels-20261028/choices.json --port 63515
```

页面只监听本机；按模板 key、版本和照片保存选择与备注，并保留 JSONL 历史。旧的 483 条标注独立保留。已核验重启后恢复、换行备注、跨站请求拒绝、无效候选/版本及备注长度校验；测试使用临时文件，未伪造用户评价。

下一步由用户在评估页选择候选或标为全部不满意，再针对被接受的方向修正模板、集成和回归。模板 skill 的 `references/review-calibration.md` 已补充本轮的能力边界、网格门槛、分阶段计时和报告保存经验。

模型来源：[GANimation 复现及预训练权重](https://github.com/donydchen/ganimation_replicate)、[3DDFA_V2](https://github.com/cleardusk/3DDFA_V2)。
