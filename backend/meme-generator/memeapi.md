# Meme Generator API 接口文档

本文档描述了表情包生成器的 Web API 接口，这些接口提供了与命令行工具相对应的功能。

## 基础信息

- **基础URL**: `https://tsoltehfuvgd.sealosbja.site`
- **Web框架**: FastAPI
- **交互式文档**: 访问 `https://tsoltehfuvgd.sealosbja.site/docs` 查看自动生成的 Swagger UI

## 接口列表

### 1. 获取版本信息
**等价命令行**: `meme --version`

```
GET /meme/version
```

**响应**:
- 返回当前版本号字符串

**示例**:
```bash
curl https://tsoltehfuvgd.sealosbja.site/meme/version
```

### 2. 列出所有表情
**等价命令行**: `meme list` / `meme ls`

```
GET /memes/keys
```

**响应**:
- 返回所有可用表情的key列表

**示例**:
```bash
curl https://tsoltehfuvgd.sealosbja.site/memes/keys
```

### 3. 渲染表情列表
**等价命令行**: `meme list` (可视化版本)

```
POST /memes/render_list
```

**请求体**:
```json
{
  "meme_list": [
    {
      "meme_key": "petpet",
      "disabled": false,
      "labels": ["hot", "new"]
    }
  ],
  "text_template": "{keywords}",
  "add_category_icon": true
}
```

**响应**:
- 返回渲染后的表情列表图片

**示例**:
```python
import httpx

async def render_meme_list():
    data = {
        "meme_list": [{"meme_key": "petpet"}],
        "text_template": "{keywords}",
        "add_category_icon": True
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://tsoltehfuvgd.sealosbja.site/memes/render_list", json=data)
    return resp.content
```

### 4. 获取表情详细信息
**等价命令行**: `meme info <key>` / `meme show <key>`

```
GET /memes/{key}/info
```

**路径参数**:
- `key`: 表情的key

**响应**:
```json
{
  "key": "petpet",
  "params_type": {
    "min_images": 1,
    "max_images": 1,
    "min_texts": 0,
    "max_texts": 0,
    "default_texts": [],
    "args_type": {
      "args_model": { /* JSON Schema */ },
      "args_examples": [
        {"circle": true}
      ],
      "parser_options": [...]
    }
  },
  "keywords": ["摸", "rua"],
  "shortcuts": [],
  "tags": ["touch"],
  "date_created": "2023-01-01T00:00:00",
  "date_modified": "2023-01-01T00:00:00"
}
```

**示例**:
```bash
curl https://tsoltehfuvgd.sealosbja.site/memes/petpet/info
```

### 5. 生成表情预览
**等价命令行**: `meme preview <key>`

```
GET /memes/{key}/preview
```

**路径参数**:
- `key`: 表情的key

**响应**:
- 返回使用默认参数生成的预览图片

**示例**:
```bash
curl https://tsoltehfuvgd.sealosbja.site/memes/petpet/preview -o preview.gif
```

### 6. 制作表情
**等价命令行**: `meme generate <key> --images <images> --texts <texts> [args]`

```
POST /memes/{key}/
```

**路径参数**:
- `key`: 表情的key

**请求体** (multipart/form-data):
- `images`: 图片文件列表 (UploadFile)
- `texts`: 文字列表 (可选)
- `args`: 额外参数的JSON字符串 (可选)

**响应**:
- 返回生成的表情图片

**示例**:
```python
import asyncio
import json
import httpx

async def generate_meme():
    files = [("images", open("avatar.jpg", "rb"))]
    texts = []
    args = {"circle": True}
    data = {"texts": texts, "args": json.dumps(args)}

    url = "https://tsoltehfuvgd.sealosbja.site/memes/petpet/"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, files=files, data=data)

    with open("result.gif", "wb") as f:
        f.write(resp.content)

# 运行示例
asyncio.run(generate_meme())
```

**curl 示例**:
```bash
curl -X POST \
  -F "images=@avatar.jpg" \
  -F "texts=测试文字" \
  -F 'args={"circle": true}' \
  https://tsoltehfuvgd.sealosbja.site/memes/petpet/ \
  -o result.gif
```

### 7. 按需求分类获取表情列表
用于减少前端多次请求的负担，直接按输入需求返回四类表情 key 列表。

```
GET /memes/categories
```

**分类规则（基于最小需求）**:
- 仅文字: `min_images == 0` 且 `max_images == 0` 且 `min_texts >= 1`
- 仅图片: `min_texts == 0` 且 `max_texts == 0` 且 `min_images >= 1`
- 图文混合: `min_images >= 1` 且 `min_texts >= 1`
- 全部: 所有表情

**响应**:
```json
{
  "all": ["petpet", "..."],
  "text_only": ["text_meme_key"],
  "image_only": ["image_meme_key"],
  "mixed": ["mixed_meme_key"]
}
```

**示例**:
```bash
curl https://tsoltehfuvgd.sealosbja.site/memes/categories
```

## 缺少的功能

目前Web API 缺少以下命令行功能：

### 下载资源
**命令行**: `meme download [--url <url>]`

此功能用于下载内置表情包所需的图片资源。目前只能通过命令行使用：

```bash
# 使用默认资源URL下载
meme download

# 指定资源URL下载  
meme download --url https://example.com/resources/
```

## 错误处理

所有接口都遵循统一的错误处理模式：

### 常见错误码

- **404**: 表情不存在 (`NoSuchMeme`)
- **552**: 参数验证失败 (`ArgModelMismatch`)
- **500**: 其他表情生成异常 (`MemeGeneratorException`)

### 错误响应格式

```json
{
  "detail": "错误信息"
}
```

## 启动服务

### 通过pip安装
```bash
meme run
```

### 源码方式
```bash
python -m meme_generator.app
```

### 使用Docker
```bash
docker run -p 3000:3000 meme-generator
```

## 配置

服务默认配置：
- 主机: 127.0.0.1
- 端口: 3000

可以通过配置文件或环境变量修改这些设置。

## 注意事项

1. 所有POST接口都需要正确的Content-Type头
2. 图片文件大小和格式有限制
3. 某些表情可能需要特定数量的图片和文字
4. 部分表情支持额外的参数配置
5. 生成的图片格式取决于表情类型（GIF、PNG、JPG等）

## 开发建议

1. 使用异步HTTP客户端（如httpx）以获得更好的性能
2. 正确处理文件上传和响应流
3. 参考 `/memes/{key}/info` 接口了解每个表情的具体参数要求
4. 利用交互式API文档进行测试和调试
