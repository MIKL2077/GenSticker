# Live 导入快捷指令

`build-live-import.py` 生成项目自己的未签名二进制 plist，包含：获取剪贴板 → 选照片 → 编码媒体（640×480）→ 使用 `X-Live-Import` 请求头上传文件 → 快速查看响应。无登录凭据、无固定导入口令，不会发送整个相册。

```
python3 tools/shortcuts/build-live-import.py
shortcuts sign --mode anyone --input /tmp/GenSticker-Live.unsigned.shortcut --output /tmp/GenSticker-Live.shortcut
```

本机 Apple 签名失败，因此目前仅交付 [首次手动设置教程](https://www.shangkun.uk/gensticker/live-setup.html)。不要将未签名文件当作可安装文件发布。签名成功后仍须在 iPhone 验证实际 Live 提取、权限提示和回传，再开放一键安装。不要将项目源码上传外部签名服务。

动作字段参考 [ScPL](https://docs.scpl.dev/actions/encodemedia) 与 [Shortcuts Playground 参数定义](https://github.com/viticci/shortcuts-playground-plugin/blob/main/claude/skills/shortcuts-playground/PARAMETER_TYPES.md)。
