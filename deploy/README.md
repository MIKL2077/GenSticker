# GenSticker 恢复与部署

源版本：`d9fd2817afb8e0af52a2602b0abf0a6371267cdc`。本项目使用模板合成图片，不需要 AI 生成 API 密钥。

## 微信小程序

```sh
cd frontend
npm ci --cache /private/tmp/gensticker-npm-cache
npm run build:mp-weixin
```

在微信开发者工具中导入 `frontend/dist/build/mp-weixin`。已配置 AppID `wx2e3a058ed0117034`。微信端默认访问下方 HTTPS 地址；如需 SSH 隧道联调，可在 `.env.local` 覆盖为 `http://127.0.0.1:3001`：

```sh
ssh -N -L 127.0.0.1:3001:127.0.0.1:3001 root@111.228.46.221
```

正式部署路由验证后，在 `frontend/.env.local` 中设置：

```dotenv
VITE_API_BASE_URL=https://www.shangkun.uk/gensticker/api
```

重新编译，并在微信公众平台把 `https://www.shangkun.uk` 加入 request 合法域名。开发工具的 `urlCheck=false` 只用于本地调试；真机发布必须配置合法域名。开发工具需要登录微信并成功下载基础库。

## 独立后端

- 源码：`/opt/gensticker/meme-generator`
- 虚拟环境：`/opt/gensticker-venv`
- 系统账号：`gensticker`（无登录 shell）
- 配置：`/var/lib/gensticker/.config/meme_generator/config.toml`
- 缓存：`/var/cache/gensticker`
- 服务：`gensticker.service`
- API：`127.0.0.1:3001`
- Nginx：`127.0.0.1:3000`（Tunnel 既有入口）和 `127.0.0.1:3002`
- 个人网站：`127.0.0.1:3003`，通过 Nginx 继续服务原域名

配置文件内容：

```toml
[server]
host = "127.0.0.1"
port = 3001
```

安装 Python 3.12 虚拟环境，安装当前源码，复制本目录的 `gensticker.service` 到 `/etc/systemd/system/`、`fonts.conf` 到 `/opt/gensticker/`、`nginx-gensticker.conf` 到 `/etc/nginx/conf.d/`。源码归 root 所有、gensticker 组可读；仅状态和缓存目录由服务账号写入。

```sh
/opt/gensticker-venv/bin/pip install -e /opt/gensticker/meme-generator
systemctl daemon-reload
systemctl enable --now gensticker
nginx -t && systemctl reload nginx
curl --fail http://127.0.0.1:3001/healthz
```

现有 Tunnel 由 Cloudflare 云端配置管理，实际云端规则仍指向 `localhost:3000`。云端管理凭据返回 401，不能依赖修改本地 ingress 文件。当前通过 Nginx 在既有 3000 入口分流：`/gensticker/api/` 转到 3001，其他路径转到网站 3003。`obsidian-gensticker-port.conf` 安装在 `/etc/systemd/system/obsidian-dev.service.d/gensticker-port.conf`，只覆盖网站启动端口，不改动其源码。

回滚此路由时，先移除 Nginx 的 3000 监听并重载，再移除网站端口 drop-in、执行 daemon-reload 和重启网站，恢复原 3000 端口。原始配置备份保存在 `/root/incident-20261013/`。
Nginx 限制请求体 15 MB；微信端图片原始总大小最多 10 MB。生成限速每 IP 每分钟 6 次，允许 3 次突发，超限返回 429。后端 JSON 生成最多同时运行两次；服务内存上限 2 GB、CPU 上限两核，不授予网络原始套接字或提权能力。

## 2026-10-13 入侵处置记录

已确认的证据：

- `guest` 的 UID/GID 为 0，拥有 root 权限。用户确认不认识此账号。
- 2026-10-11 15:19:45（北京时间）SSH 日志记录 `217.128.86.8` 成功登录 `guest`。
- 扫描目录于 10 月 11 日 15:28 创建，screen 中的循环脚本持续运行。
- 10 月 13 日 14:27 启动的扫描子进程使用 `masscan 164.0.0.0/8 -p22 --rate=25000`。
- 父脚本无限循环扫描并通过 PHP/parallel 进行 SSH 密码爆破。
- guest 的 `.bashrc` 包含 `unset HISTFILE` 和执行 `/var/www/httpd/hma` 的命令。
- 旧防护仅清理爆破子进程，遗漏 masscan 和循环父脚本。

已执行：暂停并终止扫描器和父进程；锁定 guest 密码、改为 nologin；在实际加载的 sshd 主配置中设置 `DenyUsers guest`，检查并重载；隔离扫描目录和 hma 程序。网站源站及公网网站仍返回 200，Cloudflare Tunnel 与网站服务正常运行。

证据存于服务器 `/root/incident-20261013/`，仅 root 可访问，包含原始认证日志、账号配置备份、扫描归档与 SHA-256。其中有敏感认证资料，不能提交 Git 或公开分享。

停止前 sysstat 当日平均出站 831.15 KiB/s；停止后 14:38 的三秒采样平均出站 0.73 KiB/s。网卡自开机累计出站约 6.12 TB（68 天）；这是操作系统计数，不能直接当作京东云本月计费流量。历史全部流量及入侵最初来源尚未完整核实。

由于攻击者获得 root 权限，不能凭当前扫描确认系统已彻底干净。后续需从可信镜像重建服务器，并迁移已核验的应用源码与数据；更换 root 认证和此服务器可访问的 GitHub 部署密钥、Cloudflare 凭据、OpenClaw/API 凭据。先备份业务数据并验证恢复，不能直接覆盖当前服务器。当前不改变 root 认证，以保留用户已有登录途径。

## 验证与当前状态

已完成微信与 H5 编译、语法检查和模拟平台请求测试。已通过真实微信模拟器 3.17.4 的文字、单图 GIF、双图 GIF、图文生成和图片预览。HTTPS 健康检查正常；294 个模板可用，“典中典”因缺少百度翻译凭据暂时禁用。静态缩略图替代列表中的动态预览，取消跨分类预加载；样本从约 4 MB 降为约 25 KB。

服务、Nginx 路由与恶意进程复活检测 timer 均已启用。限速验证返回 429，超大请求返回 413；网站返回 200。生成链路的验证截图保存在本目录。root 的现有认证未改变，未新增 SSH 公钥。

微信登录、历史与收藏恢复见 PRODUCT_DESIGN.md。真实微信登录、收藏同步、浏览历史及从收藏重新打开模板均已通过模拟器验证。`backend/meme-generator/tests/test_account.py` 使用隔离数据库和模拟微信提供方验证未登录拒绝、用户隔离、幂等、记录数量限制、过期及撤销；`frontend/tests/library.cjs` 验证游客记录、迁移和退出后的缓存隔离。

AppSecret 保存在服务器 `/etc/gensticker.env`，权限 600，只由 systemd 读取，不能提交 Git。账户数据库是 `/var/lib/gensticker/accounts.sqlite3`，备份业务数据时包含数据库及 WAL 文件，最好暂停此独立服务后备份。新的环境应安装 `config.toml` 并按需配置 `WX_APPID`、`WX_APP_SECRET`、`GENSTICKER_STATE_DIR`。服务即使没有微信密钥也能运行生成和游客功能。

GitHub 分阶段提交使用 codex/restore-wechat-final 分支，已通过仓库专用 SSH 部署公钥恢复推送。微信小程序尚未发布；发布前需在平台配置 request 合法域名、隐私说明，并完成扫码真机验证。

## 2026年10月14日 性能与登录修复

列表与历史/收藏预览不再把图片 Base64 写入 Vue 页面状态，改用 `downloadFile` 临时文件路径；模板详情、缩略图与分类请求复用并缓存，失败请求不进入成功缓存。保留当前页及下一页预加载。首页卡片放大预览并调整文字与间距，详情与登录弹窗统一圆角、遮罩和关闭按钮。

生成前对超过1280像素的 JPEG 等比缩小并压缩；透明图、动图保持原格式。JSON 请求仍最多10MB原始文件，超时错误明确显示，429与503区分提示，重复生成按钮调用被抑制。注意：当前10MB是允许上限，弱网络上传仍可能较慢；未引入新需求的AI流水线。

原截图是 `request:fail timeout`，不能直接当作后端异常。10月13日17:28:51的 `always/generate` 请求在 Nginx 为400，应用日志没有对应正常生成记录；旧访问日志缺少耗时，错误日志没有进一步线索，不能唯一定位最初网络故障。独立服务本地生成1280×960 JPEG样本200，耗时约0.49秒；微信模拟器通过原页面入口生成“一直”模板成功，打开模板到本地结果约5.6秒。当前无法复现原超时，不宣称已经排除所有弱网络或大动画导致的超时。

Nginx 已增加请求总耗时、上游耗时、接收及发送字节日志，并取消 User-Agent、Referer 等无关字段；诊断错误日志为 `/var/log/nginx/gensticker-error.log`。不记录 Authorization、登录 code、AppSecret、请求体和头像内容。新日志轮转需沿用系统 `/var/log/nginx/*.log` 配置。

未登录点头像、历史记录、收藏模板会打开微信登录弹窗，使用 `chooseAvatar` 与 nickname 输入框。登录后头像入口用于修改个人资料；历史/收藏直接打开。登录配置预加载，记录同步在后台完成，已缓存记录立即可用，前台重复展示30秒内不重复拉取。昵称与规范化128×128 JPEG头像保存于用户数据库，头像接口仅返回当前用户资料；前端写头像本地文件，避免 Base64 长期占用页面状态。此变更允许用户主动上传头像，需在小程序平台更新对应隐私用途说明。

已通过三组前端测试：library、weixin-generation、thumbnail-cache；生成测试覆盖 JPEG 缩小、超时与限速提示。后端5项账户测试覆盖头像校验、128像素归一化、昵称与用户隔离。微信/H5构建通过；模拟器验证未登录历史入口弹窗、真实微信登录、昵称保存后自动进入历史页面。没有自动选择用户微信头像，头像选择仍由用户操作；真机弱网络与大动画仍需现场验证。

服务端资料接口与 Nginx 已部署，网站200，API健康检查294模板，gensticker/nginx/cloudflared/obsidian-dev均active。前端在本地开发者工具已构建验证，尚未上传或发布微信小程序。

新需求设计见 [NEXT_FEATURES_DESIGN.md](NEXT_FEATURES_DESIGN.md)，仅设计，未创建采集任务或启用模型/API。
