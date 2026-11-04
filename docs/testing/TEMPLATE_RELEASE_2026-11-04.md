# 2026-11-04 主题模板评审入库

用户已完成本地审核并明确要求按结果入库。读取 `output/template-expansion-20261103/reviews.json`，20 项全部有逐项结论：16 项通过、4 项不要。只导出通过项，并核对配方哈希与评审时版本完全一致。

- 奶龙 GIF：N01、N02、N05、N06、N07、N09。
- 中文日常：Z01、Z02、Z03、Z04、Z06、Z07、Z09。
- 主内：C03、C04、C05。
- 不发布：C01、C02、Z08、Z10。已知缺陷 C02、Z10 仍保持不发布。

使用 `tools/collect/release_themed_review.py` 生成私有发布包，包含 198 个去重素材、原始评审快照、明确排除列表。保留来源 URL、作者未知情况、`license: unverified`，只记录真实的用户视觉批准。模板仍为改字模板，不进入上传照片推荐池。

发布包 SHA-256：`e85743a0ed4fae4c7d9eaef8cedcdcfe7f2124e5447ab5651d8f4dd568f817bd`。

本地隔离状态和服务器 Linux 隔离状态分别通过完整发布检查：素材哈希和格式、评审绑定、默认文字、真实替换文字、空文字渲染。原始导出还核验了已有多行和溢出验证结果。通过后用生产运行时的 `catalog.publish` 写入生产数据库，未替换运行时代码、未重启服务。所有模板从版本 1 开始，保留稳定 key/UUID。

生产状态目录 `/var/lib/gensticker`。生产发布回执和发布前 SQLite 快照位于：

`/var/lib/gensticker/features/reviewed_releases/e85743a0ed4fae4c/`

本地回执：`/Users/shangkun/Documents/ChatGPT/GenSticker/output/template-release-20261104/production-receipt.json`。

发布前总量 994，发布后总量 1010。API 与 worker 均 active，NRestarts 均为 0。

生产 HTTP 验证通过：16 项均存在于目录、信息接口可读、原始示例图片可解码、真实替换“测试”文字可生成；6 个 GIF 示例保持完整源帧数，替换输出仍为多帧，4 个拒绝项不在目录。本机公网目录也已确认 1010 项，但后续公网批量请求受到 HTTP 429 限流；服务器访问公网域名返回 403，所以不能把直连 HTTP 的全量检查宣称为公网全量检查。本地 API 验证回执位于 `output/template-release-20261104/api-verification.json`。

回滚应按回执逐 key 核对当前 version/fingerprint 后，将此次新增的模板标记 withdrawn；不要恢复旧数据库覆盖后来用户的数据。发布工具对已存在 key 拒绝覆盖，异常时只撤回本包新 key，保留版本历史。

## 微信验收状态

2026-11-04 再次调用官方微信开发者工具 CLI，获取 AppID 权限仍失败，错误 `UNABLE_TO_VERIFY_LEAF_SIGNATURE`。没有关闭 TLS、域名校验或接受不安全代理。

按用户授权打开 iPhone 镜像，截图确认可看到真实手机微信；通过镜像键盘快捷键和 Spotlight 成功启动微信。但是镜像点击、滚动均报 `noWindowsAvailable`，即使重新获取窗口并 Raise 仍无法完成触摸操作。因此尚未完成最新开发版本的真机示例分享、GIF 连续播放和交互流畅度验收。已请用户打开包含“分享这张示例”按钮的最新版本并修复网络证书，后续需继续真实验收。

## 10:53 证书问题进一步定位

用户确认线上小程序名称为“损友表情生成器”，并已手动打开；镜像截图可见首页。随后尝试模板详情点击，镜像接口仍报 `noWindowsAvailable`，此问题独立于开发者工具证书问题。

读取历史聊天“为生成队列添加拼图功能”（`01a195cf-db26-7630-842f-c9ece185b7c7`），确认 11 月 1 日官方 CLI 的交互验收和预览码生成均曾成功。没有证据可确定其后具体发生过哪次代理或证书配置变化。

本次只读诊断：

- `scutil --proxy` 当前没有启用 HTTP/HTTPS 系统代理，shell 无相关代理或额外 CA 环境变量。
- Reqable 仍在监听 TCP 8888。
- 开发者工具“设置 → 代理设置”当前选中“使用系统代理”。未修改设置。
- Node HTTPS 请求 `https://servicewechat.com/`：直连 TLS 验证成功，`authorized: true`，证书签发者 DigiCert；根路径 HTTP 404，表示 HTTPS 已成功到达服务。
- 同一 Node 请求显式经 `http://127.0.0.1:8888`：复现 `UNABLE_TO_VERIFY_LEAF_SIGNATURE`。
- Mac curl 对同一域名直连和经该代理均能验证并收到 HTTP 404，说明 curl 与 Node 的 CA 信任行为有差异，不能用浏览器/curl 可访问推断开发者工具 Node 也可访问。

由此证实 Reqable 路径存在 Node 证书信任链问题；开发者工具是否缓存此前系统代理路径需要完全退出并重启验证，不能仅因当前系统代理关闭就排除运行中旧配置。优先处理方案是在工具中明确选择直连并完全重启。需要继续抓包时，可按 Reqable 官方 SSL Proxying 文档让微信域名透传，不解密该连接；若必须解密，应核验并正确配置该本机 CA 的信任链。未修改网络设置、安装/信任新根证书或关闭 TLS/合法域名校验。
