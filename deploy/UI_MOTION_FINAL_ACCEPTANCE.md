# 透明Logo、排行榜配色与动效补充

2026年10月18日。本次保留用户已认可的页面布局，接续 [上一版记录](UI_TOY_STYLE_ACCEPTANCE.md)。

## 视觉改动

- 首页和AI页主视觉使用 `frontend/src/static/logo-subject.png`，透明PNG，480×289，约34KB。移除浮动Logo的方形底板、边框和底板阴影，保留面具图案及GenSticker字标。原 `logo.png` 未被本次修改覆盖，仍可用于头像等场景。
- 排行榜保持三人展台布局，改为暖白与浅蜜桃背景、珊瑚橙冠军台、杏色亚军台及浅金色季军台，替换大面积绿色。标题、说明与热力值同步调整为暖棕色。
- Logo保留悬浮、轻微三维旋转及点击回弹；装饰星星、小圆球轻微闪动/浮动。排行模板轻轻悬浮，展台依次入场，冠军星标轻闪。
- 分类与分页选中弹性反馈、模板卡片错峰入场、缩略图淡入、未加载占位扫光；制作弹窗摘要与输入区入场、上传提示、收藏反馈、编辑/预览图片淡入与生成提示；AI步骤、结果选中、换批/保存操作反馈；个人中心、收藏历史卡片入场及底部导航反馈。

动画主要使用transform/opacity，没有新增动效依赖、WebGL或JS逐帧循环。持续动画随页面隐藏暂停；首页制作弹窗或生成预览打开时，Logo与排行榜动画暂停，关闭后恢复。减少动态效果偏好下关闭装饰动画及扫光。没有做低端真机帧率测量，不将CSS动效等同于所有设备无卡顿。

## 图片处理

使用内置imagegen工具，编辑对象为现有Logo。提示词：

> Use case: background-extraction. Edit target: the provided existing GenSticker brand logo. Remove ONLY the ivory/off-white background so the background is genuinely transparent. Preserve the exact existing two overlapping cyan-blue happy and yellow sad theatre masks, coral ribbon accents, dark navy outlines, and exact GenSticker lettering underneath. Preserve original shape, proportions, placement, expression, colors, and letterforms. Do not redesign, reinterpret, stylize or add 3D effects. Keep mask mark and full wordmark together. No square tile, badge, outline around the whole logo, white border, ground plane, new shadows, extra text or decorations. Output only the existing logo subject and wordmark on alpha transparency, with tight clean edges and modest transparent padding.

生成后使用Sharp裁掉透明外边距、缩小并优化PNG后保存至项目。此过程只处理新的透明版本，保留原品牌文件。

## 构建、同步与检查

- 9组前端回归通过，H5及微信小程序生产构建通过，`git diff --check`通过。
- H5在390×844、320×568检查主视觉和排行榜，没有横向溢出。通过计算样式确认主视觉底板背景透明、底板阴影为none；打开制作弹窗时三个排行卡片及Logo的animation-play-state均为paused，关闭后排行恢复running。
- 截图：`deploy/ui-motion-final/home.jpg`、`my.jpg`、`ai-guest.jpg`。本地预览仍是项目示例素材接口，不代表线上生成验收。
- 使用项目的 `npm run open:mp-weixin` 和微信官方CLI导入更新。窗口名：`GenSticker-public-vc3Siq`。实际项目目录：`/var/folders/h5/m6p8phbn7799tx4wjrmx6cvr0000gn/T/gensticker-weixin-preview-vc3Siq`。
- 最终构建再次同步到该目录，80个产物逐文件SHA256一致；保留工具自己的project.private.config.json及该预览项目名称。AppID仍为wx2e3a058ed0117034，域名校验保持开启，API仍为原公网HTTPS地址。
- 官方CLI报告open成功，并已对该预览项目执行一次关闭/重开；开发者工具日志两次出现 `routeTo appLaunch timeout`，因此只确认代码构建、同步和导入成功，尚未确认模拟器运行及微信真机效果。没有上传微信版本或发布。
