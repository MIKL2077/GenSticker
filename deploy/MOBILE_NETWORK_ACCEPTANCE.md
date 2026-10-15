# 真机首页网络诊断与域名配置

2026-10-14。用户提供的真机截图显示分类为 0、目录加载失败；随后提供的微信后台配置截图中，request 域名仅有旧服务地址，uploadFile 和 downloadFile 为空，未包含当前 `www.shangkun.uk`。已确认存在服务器域名配置缺失，但尚未收到保存后的真机复测结果，不将模拟器成功当作真机修复证明。

## 后台应填写

- request 合法域名：在已有地址末尾用英文 `;` 分隔，添加 `https://www.shangkun.uk`，保留已有地址。
- uploadFile 合法域名：`https://www.shangkun.uk`。
- downloadFile 合法域名：`https://www.shangkun.uk`。
- DNS 预解析域名可填 `www.shangkun.uk`，预连接可填 `https://www.shangkun.uk`。
- 当前不使用 socket / UDP / TCP；无需填写这些域名。

只填主机域名，不填 `/gensticker/api`。代码 API 前缀仍是 `https://www.shangkun.uk/gensticker/api`。保存配置后退出小程序，重新扫码检查。微信配置页被浏览器工具安全策略明确阻止访问，无法代替用户提交或通过其他入口绕过；本轮由用户手动保存域名。

## 已完成的代码与服务修复

首页错误不再一律显示“请检查网络”：可区分 `DOMAIN_NOT_ALLOWED`、`NETWORK_TIMEOUT`、`DNS_ERROR`、`TLS_ERROR`、`ACCESS_DENIED` 和 HTTP 状态；域名校验失败或 403 不反复重试。错误提示不显示账户凭据。

首次目录超时从 10 秒调整至 25 秒，最多两次尝试，允许弱网连接和传输完成。模板命中缓存的交互不增加等待。公开目录增加 JSON gzip 压缩，保留原有读请求限速；其他项目和私有接口的配置未修改。

## 证据与限制

- 本机普通客户端与 iPhone 微信 User-Agent 访问公网健康检查均 HTTP 200，约 6.1 / 6.5 秒；仅验证该测试网络，没有假装是真机请求。
- 公网目录 HTTP 200，未压缩 151,649 字节；压缩后实际传输 23,869 字节，响应 `Content-Encoding: gzip`，本次请求约 6.8 秒。后端仍有 295 个模板。
- 新增网络错误回归测试，加上既有共八组前端测试通过；微信和 H5 构建通过。
- Nginx 配置检验通过并已重载，备份位于 `/opt/gensticker/backups/pre-mobile-network-20261014/nginx.conf`。

缺失域名配置可导致真机在发送前拒绝请求。域名补齐后仍应验收；如果继续失败，新版错误码能指明后续需要处理的连接层。当前不宣称已排除所有运营商 / DNS / 公网入口问题。

## 保存配置后仍报错的进一步定位

用户保存后仍出现 `DOMAIN_NOT_ALLOWED`。项目此前关闭域名检查，模拟器的成功无法验证许可；现已将源码 `manifest.json` 的 `urlCheck` 设为 true。本机当前项目的 private 配置也开启校验，清理其网络 / 编译缓存并重启工具后仍能复现。

读取当前 AppID 的本地项目元数据，发现原项目 attr / runtimeAttr 仍是三个旧 Sealos request 域名，上传、下载列表为空。通过官方 CLI 正常导入同 AppID、相同构建的新预览目录后，微信返回的三份名单都已包含 `https://www.shangkun.uk`。开启校验的实际请求返回 HTTP 200，独立新调试会话中的首页加载 295 个模板，错误为空。该证据定位到了旧项目缓存，而非新增后台服务故障；保存后的真机复测仍待用户验收。

直接同步旧权限缓存的操作被自动审批拒绝，理由是可能绕过正常平台校验；操作未执行且已放弃。采用官方正常导入的新预览项目，不编辑许可缓存、不关闭校验。新增 `frontend/scripts/preview-weixin.cjs`：构建时核验 AppID 和校验开关，每次预览从新目录正常获取当前配置，保留源码与用户数据，避免再携带旧项目元数据。

## 2026-10-15：避免再次打开旧项目窗口

用户再次提供 macOS 开发工具日志，许可名单为旧三个 Sealos 域名和工具自动加入的 tcb-api。只读检查确认：原 `frontend/dist/build/mp-weixin` 项目记录仍缺少当前域名，先前正常导入的项目记录已包含当前域名。README 的旧导入说明会把测试者引回旧目录，现已修正。

新增 `npm --prefix frontend run open:mp-weixin`，构建后通过官方 CLI 正常导入新目录，并关闭本仓库旧 build / dev 项目窗口；新窗口命名为 `GenSticker-public-…`，终端打印路径和公网后端地址。预览命令使用相同流程，保持 `urlCheck: true`，不修改权限记录。代码修改后需重新运行命令，临时目录是构建快照，不是源码目录。

本轮新项目实际取得的 request / upload / download 名单均包含 `https://www.shangkun.uk`。开启校验的 `wx.request` 健康检查 HTTP 200，返回 295 个模板；重开独立调试会话后首页 Vue 实例加载完成，分类计数 `[295, 68, 175, 5]`，`loadError` 为空。构建、脚本语法和网络错误回归测试通过，已生成新私有预览二维码。自动化首次启动的页面桥接曾未初始化，重开后验证通过；真机仍以用户扫码验收为准。
