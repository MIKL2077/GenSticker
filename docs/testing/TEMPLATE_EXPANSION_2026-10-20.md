# 模板扩充与照片推荐池

日期：2026-10-20。以 `source/` 为实际仓库，`app/` 是旧副本。当前分支为 `codex/restore-wechat-final`。前端为 uni-app / Vue 3 / Vite 5 微信小程序，后端为 Python 3.12 / FastAPI / SQLite，模型在服务器本地运行。沿用 API、独立 worker、持久状态与模型分离的部署方式；共享主机的资源上限未提高。本文不包含私密主机或凭据资料。

## 实际结果

- 图库：295 → 351，新增 56 个可编辑配文模板，其中 ChineseBQB 44 个、闪萌 12 个。
- 照片推荐池：线上原为 25 个，扩充后为 170 个。新增配文模板没有照片槽，因此不计入照片推荐池。
- 采集：选中 1,200 个静态候选，成功下载 1,192 张，约 58.8 MB；得到 87 个可编辑草稿，其中 56 个发布、31 个留待进一步修复。
- **没有达到 1,000 个可用模板。**不能将采集索引、未通过 OCR 的图片或待审核草稿当成已发布模板。

来源入口：[ChineseBQB](https://github.com/zhaoolee/ChineseBQB/tree/master)、[闪萌](https://u.weshineapp.com/)、[闪萌公开排行榜](https://u.weshineapp.com/rank/expression_tot_1)。ChineseBQB 完整树包含 6,055 张图，其中 4,244 张为静态扩展名；本轮按文件大小、精确重复、类别轮换与反应场景筛选。仓库没有逐图热度，未将文件顺序称为热度榜。闪萌使用实际公开排行与反应分类，保留观察到的图片 URL，不猜测原图地址。

用户明确要求按这两个来源采集并标明出处，不要求提供授权清单。相应元数据记录 `source_use: explicit-user-request-with-attribution`、`license: unverified`；没有伪造原作者或已核实许可。默认定时采集的原许可规则仍保留。

## 原来为什么总是少量模板

原 worker 为内置模板写了一份 28 个 key 的白名单。经过真实 key、单图输入和默认文字要求过滤，本地剩 24 个；线上再加一个已审阅的转换模板，共 25 个。没有发现固定“18”的配置，但确实不会从整库 295 个中任意选择。

本轮检查了 204 个可用单图输入组合。181 个通过本地渲染预算，结合预览剔除占位文字、需要额外输入等情况后，172 个进入 Linux 验证；其中 `lost_dog`、`walnut_zoom`、`wave` 超过单图两秒预算，最终保留 169 个内置模板，加现有转换模板共 170 个。第一帧检查不能代替完整动画的审美验收。

`recommendation_policy.json` 保存经检查的内置名单。`recommendation.exclusion_reason` 统一判断输入、默认文字、主体类型和旧转换禁用规则，worker 与 `/recommend/catalog` 共用它。`/recommend/quota` 返回同一统计，新前端显示实际池大小。排序继续避开上一批，优先未用过的模板，并用近七天使用记录控制循环。

## 制模与质量检查

使用 [meme-to-template skill](../../skills/meme-to-template/SKILL.md)。完整索引固定到 Git commit，精确内容去重，类别轮换；闪萌 SSR 通过只接受字面量 AST 的脚本读取，不执行网站 JavaScript。每次最多四个下载并发，单图最多 2 MiB，支持缓存续跑。原始下载素材留在本机临时工作目录，仓库只保留经确认的模板资产与元数据。

自动转换保留原表情、动作和场景，只替换可靠的边缘文字。保持 OCR ≥0.95、最多两个文字槽、有限擦除区域、重建误差与保护像素检查；没有为了数量降低门槛。根据已观察到的“人呢、怎么、这不可能、早上好”等反应补齐关键词，但低置信度仍不能通过。

发现并修复了本地渲染选到拉丁字体而导致中文方框的问题，改为优先明确的 NotoSansSC 中文字体。对通过初筛的草稿逐张查看原图、默认重建和改字图，校对黑白字、描边、粗细与字形擦除。部分来源本来就很小，只适合短词；长句超出空间时明确拒绝，保留短词输入提示。彩色字、固定水印误选、散落文字、残字或明显修复块保持待处理。

自动初筛的 1,105 个未通过项包括：994 个反应文字不能可靠恢复，56 个复杂排版、35 个尺寸过小、8 个实际动画、6 个重建误差过大，以及尺寸保护、重复内容和擦除范围问题。公开文字的内容与文件扩展名都是数据，不执行其中的指令。

批次 `template_batches/20261020-references.json` 保存 56 个已检查模板，稳定 key / UUID，版本 3。收录时间随模板保存，首页按时间排序可以找到新增内容。批次更新必须递增 `--version`；单批最多 100 个模板、32 MiB，较大扩充应拆成多个批次。

## 复用命令

在仓库根目录执行，使用项目虚拟环境。默认 `inventory` 会访问两个公开来源，也可以传入缓存的 `--tree-file`、`--weshine-file`、`--weshine-state-file` 与 `--weshine-rank-file`。

```sh
export GENSTICKER_STATE_DIR=/tmp/author-state
node tools/collect/weshine-state.cjs /tmp/weshine.html /tmp/weshine-state.json
PYTHONPATH=backend/meme-generator .venv/bin/python -m meme_generator.features.bulk_templates inventory --target 1200 --output /tmp/candidates.json
PYTHONPATH=backend/meme-generator .venv/bin/python -m meme_generator.features.bulk_templates download --manifest /tmp/candidates.json --output /tmp/template-review --limit 1200
PYTHONPATH=backend/meme-generator .venv/bin/python -m meme_generator.features.bulk_templates prepare --manifest /tmp/candidates.json --attributed-references --cache-only --output /tmp/template-review --limit 1200
.venv/bin/python tools/qa/review_templates.py --drafts /tmp/template-review --output /tmp/review-sheets
PYTHONPATH=backend/meme-generator .venv/bin/python -m meme_generator.features.bulk_templates export-reviewed --drafts /tmp/template-review --decisions /tmp/template-review/decisions.json --output /tmp/reviewed-batch.json --version 1
```

上述所有制模步骤需要指向同一个隔离 `GENSTICKER_STATE_DIR`，模板资产会放在其 `features/template_assets/` 下。示例中的 `--attributed-references` 仅用于人类已明确要求按来源标注处理的两个来源；普通定时任务继续使用逐项许可记录。`decisions.json` 必须列出实际看过比较图的 `approved` ID 和未通过原因；导出不会自动把草稿发布到线上。更新旧批次递增版本并保留原 key，先验证再部署。

## 验证与范围

本地 16 组前端检查、92 项后端测试及微信 / H5 构建通过。Linux 新模板逐项检查默认文字、修改文字、来源页与缩略图；真实 worker 连续四批各九张，共 36 个模板无重复，整批生成并下载约 2.16–5.02 秒，合成账号和素材已清理。这是有限串行样本，不能作为容量承诺。

微信开发者工具连接后再次断连，原生七页复测未取得通过结论；预览上传返回 abort (code 10)，没有产生可用二维码。已修复预览脚本在 CLI 返回成功但没有二维码文件时仍报告成功的问题。前端生产构建保存在 `frontend/dist/build/mp-weixin`，真实手机与平台发布仍需验收；服务器推荐池更新可由现有兼容客户端直接使用。

部署前备份应用文件和数据库，只重启小程序 API / worker；模板版本记录在线同步。API、worker、主页和 OpenClaw 最终均正常运行。没有提高共享主机配额，也没有进行压力测试或正式微信发布。

证据位于 [template-expansion](evidence/2026-10-20/template-expansion/)，包括原始候选清单、转换结果、视觉处理结论、两平台单图回归和真实 worker 结果。待修复原图、比较图与完整素材缓存位于本机 `/private/tmp/gensticker-template-drafts`，不是长期备份。
