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
