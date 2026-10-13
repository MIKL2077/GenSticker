# GenSticker 恢复与部署

源版本：`d9fd2817afb8e0af52a2602b0abf0a6371267cdc`。本项目使用模板合成图片，不需要 AI 生成 API 密钥。

## 微信小程序

```sh
cd frontend
npm ci --cache /private/tmp/gensticker-npm-cache
npm run build:mp-weixin
```

在微信开发者工具中导入 `frontend/dist/build/mp-weixin`。已配置 AppID `wx2e3a058ed0117034`。默认访问 `http://127.0.0.1:3001`，用于 SSH 隧道联调：

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
- Nginx：`127.0.0.1:3002`，限定 `/gensticker/api/`

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

Cloudflare Tunnel 配置必须在已有 `www.shangkun.uk` 网站规则之前加入这一条，保留已有规则与最终 404 规则：

```yaml
  - hostname: www.shangkun.uk
    path: /gensticker/api/.*
    service: http://127.0.0.1:3002
```

先备份 `/root/.cloudflared/config.yml`，执行 `cloudflared tunnel --config /root/.cloudflared/config.yml ingress validate`，验证成功后重启 tunnel，并验证网站和 API。新增子域名需要可用的 DNS 写入权限；当前服务器上的 CF_API_TOKEN 返回 403。

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

已通过：微信与 H5 编译、修改后的 JavaScript/Python 语法检查，以及微信请求逻辑测试（`node frontend/tests/weixin-generation.cjs`），涵盖多图与多文字传输、二进制图片写入、原生分享、仅文字生成及服务繁忙错误。该测试使用模拟平台 API，不能替代真实模拟器端到端验证。已在微信开发者工具导入项目；工具显示未登录和基础库下载失败，尚未完成模拟器端到端验证。

已上传后端资源与服务配置，创建独立账号与目录。依赖安装在后台进行；后端服务启用、Nginx 配置和 Tunnel 新路由仍需执行并验证。自动审批服务出现容量不足和超时，相关后续操作未执行，等待授权恢复。尚未发布微信小程序，尚未向 GitHub 推送修改。
