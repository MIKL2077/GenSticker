# 2026-10-19 夜间修复与真实接口验收

## 当前结论：尚未全部完成

已修复本地前后端兼容、身份检查和编译配置，并改为真实接口联调。现有线上模板与合成功能可用。新版后端尚未部署，微信模拟器报错尚未获运行时验证，后台登记的真实AppID尚未读取确认；不能宣称整个小程序已经修好。

## 已完成

1. 本机系统HTTP/HTTPS代理指向127.0.0.1:6789，域名解析为198.18段代理地址。直接curl曾SSL超时；显式使用既有代理后，公网健康检查、目录和生成成功。未关闭TLS证书验证或小程序合法域名校验，未修改系统代理。
2. 本地5188预览已经从18项示例接口切到真实线上API，展示295个模板。通过页面打开“皇帝龙图”、输入文字、提交并看到真实生成结果。Vite增加可选VITE_PROXY_URL，微信构建仍固定为原公网HTTPS地址；旧示例接口未被当作后端验收。
3. `deploy/verify-live-backend.py` 实测8项请求均为200，包括健康、目录、登录配置、OpenAPI、缩略图、文字生成、图片生成、去背景。所有图像用Pillow校验，保留格式、尺寸、字节数和SHA256。结果见 [report.json](live-backend-verification/report.json)，生成图和浏览器截图在同目录。
4. 核对线上OpenAPI后确认仍为旧CreateJob：asset_id必填，无previous_job_id。前端改为只在服务端明确声明features.reroll时启用换批；旧服务器显示待更新提示，保留已有结果，不再发送注定422的请求。这是兼容处理，不是把未部署的换批功能算成已上线。
5. 新后端quota声明换批能力；account/config仅增加公开app_id，绝不返回AppSecret。微信登录前，在后端提供公开AppID时核对真实运行AppID；不一致则阻止向错误服务提交登录凭证，保留本机收藏历史。H5仍明确提示微信内登录。
6. manifest中ES6与增强编译同时开启，修正两者不同步。预览脚本从manifest读取AppID，不再维护另一份硬编码ID。当前本地AppID仍为wx2e3a058ed0117034，未凭猜测改成其他ID；顶层manifest.appid是uni-app应用标识，不应误填微信AppID。
7. 微信/H5构建及9组前端回归通过；持久本地.venv中的30项后端功能测试、6项账户测试通过。新增测试覆盖公开AppID不泄漏密钥、身份不一致不登录、旧后端不发送不支持的换批请求。
8. 最新80个微信构建文件已经逐个校验并同步到开发者工具项目GenSticker-public-vc3Siq。项目配置appid与manifest一致，es6=true、enhance=true、urlCheck=true，并已重新打开。

开发者工具目录：`/var/folders/h5/m6p8phbn7799tx4wjrmx6cvr0000gn/T/gensticker-weixin-preview-vc3Siq`。

真实联调命令：

```sh
cd frontend
VITE_API_BASE_URL=/api VITE_PROXY_TARGET=https://www.shangkun.uk/gensticker/api VITE_PROXY_URL=http://127.0.0.1:6789 npm run dev:h5 -- --host 127.0.0.1 --port 5188 --strictPort
```

## 尚未解除的三个阻塞

- **微信后台读取被安全策略拦截。** 浏览器明确拒绝访问mp.weixin.qq.com/wxamp/index/index，并禁止通过其他浏览器或间接方式绕过。因此无法按后台核对AppID、账号名称、合法域名与已发布版本，不把本地配置一致当作后台身份已确认。需要用户提供后台的公开AppID等信息，或使用平台允许的导出方式；不需要把AppSecret发到聊天里。
- **微信官方诊断授权未完成。** wechatide以真实客户端名Codex发起授权后返回Waiting for user authorization。授权任务auth_a12040c45349d9077c885ab496168b313b0249fd549a33c5多次查询仍为pending；未改用其他客户端名或绕过授权。此前工具日志存在routeTo appLaunch timeout，修正增强编译后已重新打开，但不能确认运行时效果。恢复时先查询该既有任务，不重复发起授权。
- **服务器部署身份被拒绝。** 现有恢复密钥、默认SSH身份及项目另一现有身份均被111.228.46.221拒绝；未尝试猜测密码、修改认证或利用接口绕过登录。线上仍无换批协议，取消每日次数的本地后端修改也不能算已生效。需恢复有效的服务器部署方式后更新API和worker。

## 已备好的后续部署

后端4个源码文件打包于 [backend-update.tar.gz](backend-update-package/backend-update.tar.gz)，SHA256清单及操作步骤见 [DEPLOY.md](backend-update-package/DEPLOY.md)。无凭据、账户库或照片。此包尚未部署。

恢复权限后：核实后台AppID及对应服务器配置；备份并部署4个文件；将两个每日限额配置设为0；同时重启API/worker；重新运行真实接口验收；通过真实微信登录完成首批、换批、收藏、退出及重新进入记录验证。不能只重编译前端。

## 诊断技能边界

使用微信开发者工具自带的wechatide-skill：`/Applications/wechatwebdevtools.app/Contents/Resources/app.asar.unpacked/wechatide-skill/SKILL.md`。其 `references/approval-policy.md` 明确要求“不得绕过交互步骤”；官方产品实际返回授权pending，所以运行时诊断未继续。没有将授权请求已发出当作已经授权。
