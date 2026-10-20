# 部署、资源、流量、备份与回滚

面向维护者。配置示例在 `deploy/`；真实主机、访问资料和私有备份位置通过私下交接。初始样本见[测试报告](testing/REPORT_2026-10-20.md)，整改后的状态见[整改记录](testing/REMEDIATION_2026-10-20.md)。

## 运行结构与资源

微信小程序通过 HTTPS 网关访问回环地址上的 API；API 写入持久队列，独立 worker 执行推荐、制模和视频。一个 worker 进程内使用有界模型线程，先不扩大进程数。

示例目标为共用的 4 vCPU、16 GB RAM、1500 GB/月主机：

- API、worker、采集和监测共属 `gensticker.slice`，共同 CPU 上限 200%、MemoryHigh 3 GiB、MemoryMax 4 GiB、TasksMax 192；API 与 worker 各自仍有 2 GiB 内存限制。
- 主页独立低权限身份，CPU 50%、内存 1 GiB；OpenClaw 独立低权限身份，CPU 100%、内存 3 GiB。代理服务仍优先考虑独立机器，降权不能替代可信重建。
- 系统、隧道、Nginx、缓存和备份仍消耗额外资源。CPUQuota 是调度上限，不能保证延迟或最低可用算力。
- API 只监听 `127.0.0.1:3001`；保持微信合法域名校验，正确限制网关代理来源。

`resource-limits.env.example` 给出默认值：每账号 256 MiB、每日上传尝试 300 MiB、100 个模板／视频／照片、200 个任务；状态目录 12 GiB、10 万文件，空闲磁盘低于 10 GiB 或可用 inode 低于 10 万时拒绝新写入。已有有效文件和数据库记录也计入预算，删除不退还当天上传尝试额度。

重请求在读取正文前限制并发为 2，忙时 503；worker 和网关仍有自己的限制。每次写入测量现有状态会带来开销，达到更大规模前应测量数据库／文件扫描耗时，不能直接提高限额扩容。

## 流量与成本

1500 GB 是整机共用额度，截图不能给出当前精确剩余量和账期。以云控制台为准，不把应用计量当账单。

应用默认规划 900 GB／账期，85% 时暂停新任务／上传，预留已有作品领取预算；达到 100% 暂停多数下载，仍保留登录、健康和删除。计数自启用后开始，按响应体字节累计；不涵盖此前用量、请求头、TLS、主页、OpenClaw、所有代理与供应商差异。`GENSTICKER_BILLING_DAY` 默认为 1，维护者必须核对真实账期后修改；该示例支持 1～28 号。

`gensticker-monitor.timer` 每 15 分钟采样磁盘、内存、负载和物理网卡增量，在估算流量达 50%／70%／85%／95% 时写 journal。物理网卡样本也只是自首次采样后的估计，重启间隙与供应商口径可能不同。**没有配置外部消息接收人，不能把 journal 告警宣传成已发通知。**需要在云控制台配置费用／流量告警并核对此前已用量。

规划可先预留应用 900 GB、其他业务 300 GB、余量 300 GB。按十进制 GB 计算：

```text
每日业务流量(MB) = 九图批次 × 3 + 视频次数 × 1 + 模板浏览次数 × 0.03
月度业务流量(GB) = 每日业务流量 × 账期天数 ÷ 1000
```

这只是保守示例，必须用实际素材、重复下载和云账单校准，不能由它推断 DAU 或容量。整改复测有一批九图结果超过 4 MB，3 MB 并非可靠上限。

## 发布步骤

1. 先完成主机可信来源、系统补丁与凭据轮换验收，再开放公众访问。密钥只进入私有后端环境文件。
2. 核对提交，在新的 release 目录准备代码与两套虚拟环境。可参考 `stage-runtime.sh`；仓库内 pil-utils 必须与后端相邻，不能使用旧 poetry.lock 降级图片依赖。
3. 安装字体、Fontconfig、FFmpeg、模型并校验哈希；测试全部启用模板、权限、私有任务、视频与删除。`pip check` 只证明依赖关系，不是漏洞扫描。
4. 备份当前代码、依赖环境、私有配置、服务单元、数据库和关联文件。检查活动任务，在短切换窗口暂停新任务。
5. 安装 unit／slice，将 `/opt/gensticker-current` 指到候选 release，执行 daemon-reload 后只重启应用服务；Nginx 先 `nginx -t` 再 reload。
6. 健康失败时自动恢复原 unit、环境和链接；不自动覆盖数据库。成功后验证真实 worker、模型、视频、私有访问及同机其他业务。
7. 构建 `frontend/dist/build/mp-weixin`，在微信开发工具导入当前 production 产物，再做真机验收；H5 构建不能替代小程序验收。

不要盲跑带旧路径的历史部署脚本。维护主页和 OpenClaw 时分别使用其新工作目录和账号，不能继续依赖 root 的原共享工作区。

## 定期备份与恢复

`gensticker-backup.timer` 每日 03:20 加最多十分钟随机延迟执行，最多保留最近 7 份成功的本地加密归档。`daily-backup.py` 使用 SQLite 在线 backup API、文件快照与 SHA256 清单，再通过 OpenSSL CMS AES-256-GCM 加密；磁盘低于 10 GiB 时停止。备份以 gensticker 低权限身份执行，仅状态与备份目录可写；指定环境配置通过 systemd 临时凭据提供。另有 50% CPU、768 MiB 内存和低 I/O 优先级。

服务器只保存接收方公钥证书 `/etc/gensticker-backup-recipient.pem`，**解密私钥和保护私钥的口令文件必须离机保存**。归档包含应用状态和指定应用配置，不含其他业务完整数据或模型二进制。模型需凭已核查来源和哈希重新取得；其他业务要有独立备份。公钥过期、加密失败或 timer 失败需要监控，不能只看定时器已启用。

安装前准备真实证书，安装脚本至 `/usr/local/lib/gensticker/daily-backup.py`，创建仅 gensticker 可访问的备份目录。先手动运行 service，取回一份归档，在离机私有目录解密、校验 manifest 和业务引用，成功后再 enable timer。公开仓库不放私钥、口令、密钥备份、数据库或主机完整审计。

```bash
# 在可信离机机器执行；私钥及口令文件路径由维护者私下配置
openssl cms -decrypt -binary -inform DER -in snapshot.cms \
  -inkey private-key.pem -passin file:private-key-password.txt -out snapshot.tgz
# 仅在私有临时目录解压；检查路径和符号链接，禁止覆盖正在运行的目录
python -m meme_generator.features.backup verify --output restored/gensticker-backup/application
```

在线数据库快照与文件复制不是跨文件事务。恢复时必须核对数据库的文件引用、账号归属、私有结果、队列与模型；引用中绝对路径应只在恢复副本中重定位，禁用副本对外微信调用。已完成同机隔离恢复 509 个引用无缺失，以及私有制作／注销／模型校验；仍需可信新机器的完整灾难恢复。

当前已经有离机加密快照，但每日新备份还需要持续离机传输。尚未配置可信异地存储和自动离机通道，不能承诺整机丢失时只损失一天。7 份本地保留不等于严格七天（失败日不会生成新份）；离机副本的保留与到期删除需单独落实，才能形成正式隐私承诺。

## 回滚和检查

保留上一个源码／虚拟环境／配置与微信版本。切回应用链接和服务单元后，校验健康、账户、私有生成、主页与 OpenClaw；不要盲目回滚数据库，不要覆盖切换后的新数据。涉及不兼容迁移时先停写并在隔离副本验证。

```bash
systemctl status gensticker gensticker-worker
systemctl show gensticker.slice -p CPUQuotaPerSecUSec -p MemoryHigh -p MemoryMax
systemctl list-timers gensticker-monitor.timer gensticker-backup.timer
journalctl -u gensticker-monitor -u gensticker-backup --since today
```

监控负责人仍需负责队列年龄、失败率、P95、CPU 节流、日志轮转、证书到期、备份完整性与真实云费用。未执行共享主机的满载压测、故意故障注入或新系统重建。
