import json
from datetime import datetime
from typing import Any, Literal, Optional
from pathlib import Path

import filetype
from fastapi import Depends, FastAPI, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, ValidationError

from meme_generator.compat import model_dump, model_json_schema, type_validate_python
from meme_generator.config import meme_config
from meme_generator.exception import (
    ArgModelMismatch,
    MemeGeneratorException,
    NoSuchMeme,
)
from meme_generator.log import LOGGING_CONFIG, setup_logger
from meme_generator.manager import get_meme, get_meme_keys, get_memes
from meme_generator.meme import CommandShortcut, Meme, MemeArgsModel, ParserOption
from meme_generator.utils import MemeProperties, render_meme_list, run_sync
from meme_generator.version import __version__

app = FastAPI()


class MemeArgsResponse(BaseModel):
    args_model: dict[str, Any]
    args_examples: list[dict[str, Any]]
    parser_options: list[ParserOption]


class MemeParamsResponse(BaseModel):
    min_images: int
    max_images: int
    min_texts: int
    max_texts: int
    default_texts: list[str]
    args_type: Optional[MemeArgsResponse] = None


class MemeInfoResponse(BaseModel):
    key: str
    params_type: MemeParamsResponse
    keywords: list[str]
    shortcuts: list[CommandShortcut]
    tags: set[str]
    date_created: datetime
    date_modified: datetime


def register_router(meme: Meme):
    if args_type := meme.params_type.args_type:
        args_model = args_type.args_model
    else:
        args_model = MemeArgsModel

    def args_checker(
        args: Optional[str] = Form(default=json.dumps(model_dump(args_model()))),
    ):
        if not args:
            return MemeArgsModel()
        try:
            model = type_validate_python(args_model, json.loads(args))
        except ValidationError as e:
            e = ArgModelMismatch(str(e))
            raise HTTPException(status_code=552, detail=e.message)
        return model

    @app.post(f"/memes/{meme.key}/")
    async def _(
        images: list[UploadFile] = [],
        texts: list[str] = meme.params_type.default_texts,
        args: args_model = Depends(args_checker),  # type: ignore
    ):
        imgs: list[bytes] = []
        for image in images:
            imgs.append(await image.read())

        texts = [text for text in texts if text]

        assert isinstance(args, args_model)

        try:
            result = await run_sync(meme)(
                images=imgs, texts=texts, args=model_dump(args)
            )
        except MemeGeneratorException as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

        content = result.getvalue()
        media_type = str(filetype.guess_mime(content)) or "text/plain"
        return Response(content=content, media_type=media_type)


class MemeKeyWithProperties(BaseModel):
    meme_key: str
    disabled: bool = False
    labels: list[Literal["new", "hot"]] = []


default_meme_list = [
    MemeKeyWithProperties(meme_key=meme.key)
    for meme in sorted(get_memes(), key=lambda meme: meme.key)
]


class RenderMemeListRequest(BaseModel):
    meme_list: list[MemeKeyWithProperties] = default_meme_list
    text_template: str = "{keywords}"
    add_category_icon: bool = True


def register_routers():
    @app.post("/memes/render_list")
    def _(params: RenderMemeListRequest = RenderMemeListRequest()):
        try:
            meme_list = [
                (
                    get_meme(p.meme_key),
                    MemeProperties(disabled=p.disabled, labels=p.labels),
                )
                for p in params.meme_list
            ]
        except NoSuchMeme as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

        result = render_meme_list(
            meme_list,
            text_template=params.text_template,
            add_category_icon=params.add_category_icon,
        )
        content = result.getvalue()
        media_type = str(filetype.guess_mime(content)) or "text/plain"
        return Response(content=content, media_type=media_type)

    @app.get("/meme/version")
    def _():
        return __version__

    @app.get("/memes/keys")
    def _():
        return get_meme_keys()

    @app.get("/memes/{key}/info")
    def _(key: str):
        try:
            meme = get_meme(key)
        except NoSuchMeme as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

        args_type_response = None
        if args_type := meme.params_type.args_type:
            args_model = args_type.args_model
            args_type_response = MemeArgsResponse(
                args_model=model_json_schema(args_model),
                args_examples=[
                    model_dump(example) for example in args_type.args_examples
                ],
                parser_options=args_type.parser_options,
            )

        return MemeInfoResponse(
            key=meme.key,
            params_type=MemeParamsResponse(
                min_images=meme.params_type.min_images,
                max_images=meme.params_type.max_images,
                min_texts=meme.params_type.min_texts,
                max_texts=meme.params_type.max_texts,
                default_texts=meme.params_type.default_texts,
                args_type=args_type_response,
            ),
            keywords=meme.keywords,
            shortcuts=meme.shortcuts,
            tags=meme.tags,
            date_created=meme.date_created,
            date_modified=meme.date_modified,
        )

    @app.get("/memes/{key}/preview")
    async def _(key: str):
        try:
            meme = get_meme(key)
            result = await run_sync(meme.generate_preview)()
        except MemeGeneratorException as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

        content = result.getvalue()
        media_type = str(filetype.guess_mime(content)) or "text/plain"
        return Response(content=content, media_type=media_type)

    @app.get("/memes/{key}/example")
    def _(key: str):
        """获取表情模版的示例图片"""
        try:
            meme = get_meme(key)
        except NoSuchMeme as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        
        # 查找示例图片文件
        meme_dir = Path(__file__).parent / "memes" / key
        example_files = []
        
        # 检查可能的示例文件扩展名
        for ext in ['.gif', '.jpg', '.jpeg', '.png']:
            example_file = meme_dir / f"example{ext}"
            if example_file.exists():
                example_files.append(example_file)
        
        if not example_files:
            raise HTTPException(
                status_code=404, 
                detail=f"表情模版 '{key}' 没有找到示例图片"
            )
        
        # 返回第一个找到的示例图片
        example_file = example_files[0]
        
        try:
            with open(example_file, 'rb') as f:
                content = f.read()
            
            # 根据文件扩展名确定媒体类型
            if example_file.suffix.lower() in ['.jpg', '.jpeg']:
                media_type = "image/jpeg"
            elif example_file.suffix.lower() == '.png':
                media_type = "image/png"
            elif example_file.suffix.lower() == '.gif':
                media_type = "image/gif"
            else:
                media_type = str(filetype.guess_mime(content)) or "application/octet-stream"
            
            return Response(content=content, media_type=media_type)
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"读取示例图片失败: {str(e)}"
            )

    @app.get("/memes/categories")
    def _():
        """按输入需求对表情进行分类并返回各分类的 key 列表。
        
        分类规则（基于最小需求）：
        - 仅文字: min_images == 0 且 max_images == 0 且 min_texts >= 1
        - 仅图片: min_texts == 0 且 max_texts == 0 且 min_images >= 1
        - 图文混合: min_images >= 1 且 min_texts >= 1
        - 全部: 所有表情
        其他（既不需要图片也不需要文字）仅计入“全部”。
        """
        all_keys: list[str] = []
        text_only: list[str] = []
        image_only: list[str] = []
        mixed: list[str] = []

        for meme in sorted(get_memes(), key=lambda meme: meme.key):
            all_keys.append(meme.key)
            params = meme.params_type
            if params.min_images == 0 and params.max_images == 0 and params.min_texts >= 1:
                text_only.append(meme.key)
            elif params.min_texts == 0 and params.max_texts == 0 and params.min_images >= 1:
                image_only.append(meme.key)
            elif params.min_images >= 1 and params.min_texts >= 1:
                mixed.append(meme.key)

        return {
            "all": all_keys,
            "text_only": text_only,
            "image_only": image_only,
            "mixed": mixed,
        }

    for meme in sorted(get_memes(), key=lambda meme: meme.key):
        register_router(meme)


def run_server():
    import uvicorn

    register_routers()
    uvicorn.run(
        app,
        host=meme_config.server.host,
        port=meme_config.server.port,
        log_config=LOGGING_CONFIG,
    )


if __name__ == "__main__":
    setup_logger()
    run_server()
