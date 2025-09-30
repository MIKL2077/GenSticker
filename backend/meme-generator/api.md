### meme-generator 后端 API 文档

本项目提供基于 FastAPI 的表情包生成服务。通过以下接口可查询表情列表、获取参数信息、生成预览图、渲染表情列表海报，以及生成具体表情图片/动图。

- **基础 URL**: 按部署而定（例如 `http://localhost:2233`）。
- **返回格式**: 成功时多为二进制图片或 JSON；错误时返回 JSON（HTTP 非 2xx）。
- **字符编码**: UTF-8

---

### 通用约定
- **图片媒体类型**: `image/png`、`image/jpeg`、`image/gif`（由服务自动判定）
- **时间字段**: ISO8601（例如 `2024-01-01T12:34:56.789Z`）
- **错误响应格式**:
  - HTTP 状态码：来自业务异常或 4xx/5xx
  - 响应体：`{"detail": "错误描述"}`
- **鉴权**: 无（请在网关层/部署层自行加鉴权）

---

## 1) 获取服务版本
- **Endpoint**: `GET /meme/version`
- **说明**: 返回服务版本号。
- **请求参数**: 无
- **响应示例**:
```json
"0.1.14"
```

---

## 2) 获取全部表情 key 列表
- **Endpoint**: `GET /memes/keys`
- **说明**: 返回所有可用表情的唯一 key。
- **请求参数**: 无
- **响应示例**:
```json
["petpet", "throw", "cover", "..."]
```

---

## 3) 获取指定表情的参数信息
- **Endpoint**: `GET /memes/{key}/info`
- **说明**: 获取单个表情的入参约束、关键词、快捷命令、标签以及创建/修改时间等。
- **路径参数**:
  - **key**: string，表情唯一标识（来自 `/memes/keys`）
- **响应体结构（MemeInfoResponse）**:
```json
{
  "key": "petpet",
  "params_type": {
    "min_images": 1,
    "max_images": 5,
    "min_texts": 0,
    "max_texts": 2,
    "default_texts": ["默认文案"],
    "args_type": {
      "args_model": { /* Pydantic JSON Schema */ },
      "args_examples": [ { /* args 示例对象 */ } ],
      "parser_options": [
        {
          "names": ["-n", "--name"],
          "args": [
            {"name": "user", "value": "str", "default": null, "flags": null}
          ],
          "dest": "name",
          "default": null,
          "action": null,
          "help_text": "名称",
          "compact": false
        }
      ]
    }
  },
  "keywords": ["拍拍", "摸头"],
  "shortcuts": [
    {"key": "pet", "args": ["-n", "张三"], "humanized": "拍拍 张三"}
  ],
  "tags": ["猫猫虫", "梗图"],
  "date_created": "2021-05-04T00:00:00",
  "date_modified": "2024-06-01T12:00:00"
}
```
- **说明**:
  - `args_type.args_model` 为该表情自定义参数的 JSON Schema；若无自定义参数，则不存在 `args_type`。
  - `default_texts` 在未传 `texts` 时用于兜底。

---

## 4) 生成指定表情预览图
- **Endpoint**: `GET /memes/{key}/preview`
- **说明**: 使用随机/默认素材生成预览图片或 GIF。
- **路径参数**:
  - **key**: string
- **请求参数**: 无
- **成功响应**:
  - Content-Type: `image/*`（自动判断）
  - Body: 二进制图片/动图
- **失败响应**: 见“错误码说明”

---

## 5) 批量渲染表情列表海报
- **Endpoint**: `POST /memes/render_list`
- **说明**: 将一组表情按照给定模板渲染成一张说明海报（带关键词、分类图标等）。
- **请求体（JSON, RenderMemeListRequest）**:
```json
{
  "meme_list": [
    {"meme_key": "petpet", "disabled": false, "labels": ["new", "hot"]},
    {"meme_key": "throw"}
  ],
  "text_template": "{keywords}",
  "add_category_icon": true
}
```
- 字段说明:
  - **meme_list**: 数组，默认包含全部表情；元素结构：
    - `meme_key`: string（必填）
    - `disabled`: boolean（默认 false）
    - `labels`: 数组，元素可为 `new`、`hot`
  - **text_template**: string（默认 `"{keywords}"`），文本模板，可使用占位符：`{keywords}`
  - **add_category_icon**: boolean（默认 true）是否显示分类图标
- **成功响应**:
  - Content-Type: `image/*`
  - Body: 二进制图片

---

## 6) 生成指定表情
- **Endpoint**: `POST /memes/{key}/`
- **说明**: 生成某个表情的图片/动图。不同表情的图片/文本数量与自定义参数要求不同，请先调用 `/memes/{key}/info` 获取约束。
- **路径参数**:
  - **key**: string
- **请求体（multipart/form-data）**:
  - **images**: 文件数组（可多次传同名字段），数量范围见 `min_images ~ max_images`
  - **texts**: 文本数组（可多次传同名字段），数量范围见 `min_texts ~ max_texts`
  - **args**: 字符串（可选），JSON 字符串，结构需符合 `args_type.args_model` 的 Schema；未提供时服务端使用该模型的默认值
- **成功响应**:
  - Content-Type: `image/*`
  - Body: 二进制图片/动图
- **失败响应**: 见“错误码说明”

### multipart 示例（cURL）
```bash
curl -X POST "http://localhost:2233/memes/petpet/" \
  -F "images=@/path/to/a.jpg" \
  -F "images=@/path/to/b.png" \
  -F "texts=你好" \
  -F "texts=世界" \
  -F 'args={"user_infos":[{"name":"张三","gender":"male"}]}' \
  --output result.gif
```

---

## 模型与数据结构说明

### MemeParamsResponse
```json
{
  "min_images": 0,
  "max_images": 0,
  "min_texts": 0,
  "max_texts": 0,
  "default_texts": ["..."] ,
  "args_type": {
    "args_model": { /* JSON Schema */ },
    "args_examples": [ { /* 示例 */ } ],
    "parser_options": [ /* 参见 /memes/{key}/info 示例 */ ]
  }
}
```

### MemeArgsModel（默认）
```json
{
  "user_infos": [
    {"name": "", "gender": "male|female|unknown"}
  ]
}
```
- 具体表情可能继承并扩展该模型；以 `/memes/{key}/info` 的 `args_type.args_model` 为准。

---

## 错误码说明（业务）
服务会返回相应的 HTTP 状态码与错误信息（`{"detail": "..."}`）。常见业务错误码如下：

- **520 MemeGeneratorException**: 通用处理错误
- **531 NoSuchMeme**: 表情不存在
- **532 TextOverLength**: 文本过长
- **533 OpenImageFailed**: 图片加载失败
- **540 ParamsMismatch**: 参数不匹配的基类
- **541 ImageNumberMismatch**: 图片数量不符（需满足 `min_images` ~ `max_images`）
- **542 TextNumberMismatch**: 文本数量不符（需满足 `min_texts` ~ `max_texts`）
- **543 TextOrNameNotEnough**: 文本或用户名数量不足
- **550 ArgMismatch**: 参数不匹配的基类（args）
- **551 ArgParserMismatch**: 参数解析失败
- **552 ArgModelMismatch**: 参数模型验证失败（例如 `args` JSON 结构不合法）

---

## 使用建议与典型流程
1. 调用 `GET /memes/keys` 获取可用表情 key 列表。
2. 针对所选表情，调用 `GET /memes/{key}/info` 获取数量约束与自定义参数 Schema。
3. 可选：调用 `GET /memes/{key}/preview` 预览样式与尺寸。
4. 使用 `POST /memes/{key}/` 以 multipart/form-data 上传图片、文本与 `args` 生成图片/动图。
5. 若需展示表情清单，可使用 `POST /memes/render_list` 渲染说明海报。

---

## 额外说明
- 若在 Linux 下遇到字体异常，可设置环境变量：`LANG=en_US.UTF-8`。
- 若部署为生产环境，请结合网关或服务编排增加限流/鉴权/缓存策略。 