# 生成队列多选拼图（2026-11-01）

生成队列新增“多选拼图”：按点选顺序选择 2～9 张已完成作品，进入拼图预览后分享或保存。选择时暂停左滑删除，未完成及失败任务不可选，刷新时清除已删除／过期作品的选择；取消多选后恢复原有预览与删除操作。

复用一键生成页的 SelectedResultsModal、createResultCollage 和微信图片分享入口。全部静态图保持原有高清 JPEG 布局；混选动图生成循环 GIF，静态图片保持不动。云端作品通过 POST /studio/jobs/collage 合成，只有本机的作品使用本机合成，服务暂不可用时自动回退。服务端只接收当前账号的任务 ID，不接收任意 URL 或上传照片，复用合成并发、大小、时长、生成频率和流量预算保护。

关闭预览或离开页面会取消后续制作，迟到成品会清理；保存尚未回调时保留其来源文件，完成后再释放。切换账号会清空选择、拼图及原图状态。

## 验证

- 前端队列交互、GIF 合成、服务端请求、一键生成页回归、队列预取、本机生成与持久队列检查通过。
- 后端工作室、拼图及流量预算检查：25 项通过。覆盖跨账号、过期、制作中、重复选择、非法 ID、损坏素材、合成期间删除、静态图、动画顺序和完整时长。
- Linux 现有运行环境使用隔离数据目录运行 11 项拼图测试通过，随后仅更新 studio.py、result_collage.py、traffic.py。API 与 worker 正常，目录仍为 994 项；新旧拼图接口均要求登录。
- 微信正式构建通过包体检查。开发者工具基础库 3.17.5 实际点击队列完成选择、混拼、预览、分享／保存入口、返回原图和缓存复用验证。混合成品为 12 帧、1200 ms、25,110 字节；静态拼图宽 688 px，无运行异常。
- 微信验收使用真实画布和文件系统；输入是隔离测试素材，分享和相册 API 使用替身，不发送测试图片、不写入真实相册。目标手机实际保存与发送仍需使用新预览包确认。

复现命令（仓库根目录）：

```sh
node frontend/tests/queue-collage.cjs
node frontend/tests/result-collage.cjs
node frontend/tests/server-collage.cjs
node frontend/tests/ui-flows.cjs
node frontend/tests/queue-preload.cjs
PYTHONPATH=backend/meme-generator:backend/meme-generator/tests/features .venv/bin/python -m unittest test_studio test_result_collage test_remediation.RemediationTests.test_traffic_budget_blocks_new_work_but_keeps_reads
cd frontend
npm run build:mp-weixin
npm run test:mp-weixin-queue-collage -- /tmp/gensticker-queue-proof
```

本机证据：[微信验收报告](../../../output/queue-collage-20261101/report.json)、[多选截图](../../../output/queue-collage-20261101/queue-selection.png)、[混合拼图预览](../../../output/queue-collage-20261101/queue-collage-preview.png)、[静态拼图预览](../../../output/queue-collage-20261101/queue-static-preview.png)、[部署记录](../../../output/queue-collage-20261101/deployment.json)、[新预览码](../../../output/queue-collage-20261101/preview.png)。
