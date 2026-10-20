# GenSticker 部署入口

目标是微信小程序。当前部署方式、资源预算、加密备份和回滚详见 [运维说明](../docs/OPERATIONS.md)；功能见 [README](../README.md)，完成状态见 [整改报告](../docs/testing/REMEDIATION_2026-10-20.md)。

运行代码与 API／worker 虚拟环境放在同一 release 目录，通过 `/opt/gensticker-current` 原子切换。`meme-generator` 与仓库内 `pil-utils` 保持相邻。状态和模型与 release 分开，服务账号无登录 shell。环境文件私有；不可把真实凭据放入这些示例。

本目录的 unit、slice、timer、Nginx 和限额文件是部署参考，必须先核对目标机器。`stage-runtime.sh` 准备候选环境，不会自动切换线上业务。历史 `apply-*` 脚本保留供追溯，不能作为当前一键部署入口。

```sh
cd frontend
npm ci
npm run build:mp-weixin
```

用微信开发者工具导入 `dist/build/mp-weixin`，保持域名校验开启，配置真实合法 HTTPS 域名。真机、隐私授权和微信审核需分别验收。

共享主机上的应用加固不能替代历史高权限事件后的可信重建和服务商侧密钥轮换。实际主机、事件记录、备份与访问资料通过私下渠道交接，不放入公开仓库。
