# GenSticker 界面重设计与验证记录

2026年10月16日的历史版本记录。10月18日的布局、动效、换批及后端变更以 [最新验收记录](UI_TOY_STYLE_ACCEPTANCE.md) 为准。当前为本地实现和开发构建，未上传微信、未发布生产版本。

## 已实现

- 奶油白背景、珊瑚橙主色、深蓝灰文字，统一卡片、字号、间距、按钮和状态色；去掉原来的大面积饱和橙色渐变与紫色分页。
- 首页提前展示分类及模板，保留热榜、探索、分页、试用模板和前三入口。模板卡片补充已有的输入需求；前三入口移到模板网格之后，探索模式不再伪装成热门名次。
- 制作面板改为原生 scroll-view 滚动内容与固定生成按钮。示例压缩为摘要，辅助说明可展开，来源仍可查看。单图只有一份输入预览，多图保留切换；编辑、删除、补图不变。
- 图片编辑器采用独立滚动区与固定完成按钮，保留裁剪比例、缩放、翻转、旋转、去背景、四步撤销及还原。只在编辑器内使用透明背景格纹，普通上传预览使用中性底色。
- 手动生成成功后保留本次输入，预览可返回继续修改；释放仍由关闭制作、换模板、离开页面负责。未改变生成协议、GIF输出和端侧回退。
- AI页增加步骤指示、独立额度错误、真实终态结果数、放大入口和固定保存区。批量保存固定任务与选择，重试只补存本次未完成项，统计回执失败不冒充相册保存失败。
- 一键登录直接执行现有 wx.login 和后台身份验证，不再强制先选择头像或填写昵称；使用账户返回的资料，新用户显示默认微信用户及品牌头像。编辑资料独立放在登录之后并自动预填；没有声称能静默取得微信真实头像昵称。
- 我的页面保留历史、收藏、资料修改和退出，增加已有AI页的快捷入口。退出立即清除本机登录态，后台用退出前捕获的令牌请求撤销，不受断网或服务错误阻塞；未完成同步仍留在原账户缓存，旧会话响应不能覆盖重新登录后的数据。
- 底部AI按钮的文字与图标共同响应点击；已存在的AI页优先返回，减少重复压栈。
- 增加面板入场、轻按反馈、结果淡入、小范围表情浮动和处理状态动效；使用 transform/opacity，取消阴影的无限动画，支持系统减少动态效果偏好。没有增加动效库、视频或持续JS动画循环。

## Logo

通过内置 imagegen 按用户图4重绘，已替换 `frontend/src/static/logo.png`，256×256 PNG，约29 KB。蓝黄面具与深蓝 GenSticker 字标，暖白底。页面实际引用同一文件，不再用平台显示不同的面具emoji充当logo。

生成提示词：Use case: logo-brand. Reference image is the supplied GenSticker app logo. Redraw this same brand faithfully as a clean high-resolution square PNG app logo. A warm ivory square background with generous padding. Center a small flat playful vector-style pair of overlapping theater masks: happy cyan blue mask at upper left and sad golden yellow mask at lower right, thick dark navy outlines, tiny coral ribbon tabs. Below the masks exact text 'GenSticker' in bold rounded dark navy sans serif, spelled G e n S t i c k e r, single line centered. Match the reference shapes, relative placement and lettering closely. Cute polished understated professional app branding. Keep mark plus wordmark together centered and filling about 70% width and 65% height. No orange outer background, no mockup, no 3D, no shadow, no gradients, no extra text, no extra objects. The entire PNG is the ivory logo tile, not a screenshot of an app icon.

## 已通过的检查

- 微信小程序与H5生产构建通过；微信包继续指向原公网HTTPS API，不受本地H5验证环境变量影响。构建目录约460 KB，非微信上传平台的压缩包测量。
- 原有八组前端测试全部通过，涵盖图片编辑、端侧渲染回退、分页、缩略图缓存、账户库、推荐接口、网络错误及微信手动生成/分享调用。
- 新增 `frontend/tests/ui-flows.cjs` 通过，覆盖一次点击默认登录、资料独立编辑、离线立即退出、旧会话响应隔离，以及批量保存部分失败后的续存。
- H5使用390×844视口检查首页、制作面板、编辑器、个人中心和AI游客入口，固定操作区可见。另以320×568检查制作面板，未出现横向溢出，生成按钮完整位于视口内。截图位于 `deploy/ui-redesign/`。

## 验证边界

当前环境访问公网模板API出现DNS失败或超时。H5预览通过临时环境变量连接只监听127.0.0.1的隔离样例接口，展示18项项目内已有示例，未改变线上目录、账户或结果。该接口用于排版验证，返回的生成图片是既有示例，不能作为真实生成质量或时延的证据。

尚未完成微信真机登录、相册授权与保存、微信分享、低端机帧率、弱网任务恢复和线上端到端验收。没有把样例交互、模拟测试或构建成功描述为真机通过，也不承诺所有设备恒定无卡顿。

## 回退

本次修改前的src和tests备份位于 `/private/tmp/gensticker-ui-before-20261015.tgz`。也可从Git恢复本次前端文件并重新构建；后端与数据库没有修改。不要覆盖后续用户改动。
