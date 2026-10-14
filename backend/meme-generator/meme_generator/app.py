import json
import base64
import binascii
import asyncio
import hashlib
import time
from contextlib import asynccontextmanager, suppress
from functools import lru_cache
from io import BytesIO
from datetime import datetime
from typing import Any, Literal, Optional
from pathlib import Path

import filetype
from PIL import Image
from fastapi import Depends, FastAPI, Form, HTTPException, Response, UploadFile, Request
from pydantic import BaseModel, Field, ValidationError

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
from meme_generator.account import router as account_router

@asynccontextmanager
async def lifespan(app):
    async def expire_private_cache():
        while True:
            await asyncio.sleep(30)
            render_cache.prune()
    task = asyncio.create_task(expire_private_cache())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        render_cache.items.clear()
        render_cache.bytes = 0


app = FastAPI(lifespan=lifespan)
app.include_router(account_router)
generation_slots = asyncio.Semaphore(2)
from meme_generator.features.render_cache import RenderCache
render_cache = RenderCache()


class GenerateRequest(BaseModel):
    images: list[str] = Field(default_factory=list, max_length=10)
    texts: list[str] = Field(default_factory=list, max_length=20)
    args: dict[str, Any] = Field(default_factory=dict)


@app.get('/healthz')
def healthz():
    return {'status': 'ok', 'templates': len(get_meme_keys())}


@app.post('/memes/{key}/generate')
async def generate_json(key: str, params: GenerateRequest, request: Request):
    """WeChat uses JSON for multiple images and receives a binary image response."""
    from meme_generator.features.catalog import refresh, loaded_versions
    refresh()
    try:
        meme = get_meme(key)
    except NoSuchMeme as e:
        raise HTTPException(status_code=404, detail=e.message)
    if any(len(text) > 2000 for text in params.texts):
        raise HTTPException(status_code=413, detail='文字过长')
    if sum(len(image) for image in params.images) > 14 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='图片总大小不能超过 10 MB')
    try:
        images = [base64.b64decode(image, validate=True) for image in params.images]
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=422, detail='图片必须为有效的 base64')
    args_model = meme.params_type.args_type.args_model if meme.params_type.args_type else MemeArgsModel
    try:
        args = type_validate_python(args_model, params.args)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    from meme_generator.features.popularity import record, actor
    identity = actor(request)
    cache_key = hashlib.sha256(json.dumps([identity, key, loaded_versions.get(key, 1), params.images, params.texts, model_dump(args)],sort_keys=True).encode()).hexdigest()
    cacheable = key.startswith('auto_') or key in {'always','petpet','my_friend','look_flat','look_this_icon'}
    cached = render_cache.get(cache_key) if cacheable else None
    if cached:
        record(key, identity, 'generate')
        return Response(content=cached,media_type=filetype.guess_mime(cached) or 'application/octet-stream',headers={'Cache-Control':'private, no-store','X-Gensticker-Cache':'hit'})
    if generation_slots.locked():
        raise HTTPException(status_code=503, detail='生成队列已满，请稍后重试')
    started = time.perf_counter()
    async with generation_slots:
        try:
            result = await run_sync(meme)(images=images, texts=params.texts, args=model_dump(args))
        except MemeGeneratorException as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)
    content = result.getvalue()
    if cacheable:
        render_cache.put(cache_key,content)
    record(key, identity, 'generate')
    return Response(content=content, media_type=filetype.guess_mime(content) or 'application/octet-stream',headers={'Cache-Control':'private, no-store','Server-Timing':f'generation;dur={(time.perf_counter()-started)*1000:.1f}'})


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
    template_id: str = ''
    version: int = 1
    attribution: dict[str,str] = Field(default_factory=dict)
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
        request: Request,
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
        from meme_generator.features.popularity import record, actor
        record(meme.key, actor(request), 'generate')
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
        from meme_generator.features.catalog import refresh
        refresh()
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

        from meme_generator.features.store import connect
        db=connect()
        try: catalog_entry=db.execute('SELECT id,version,metadata FROM templates WHERE key=?',(key,)).fetchone()
        finally: db.close()
        attribution={k:json.loads(catalog_entry['metadata']).get(k,'') for k in ['author','license','source_url','license_url']} if catalog_entry else {}
        if not attribution.get('source_url'):
            attribution={'author':'MemeCrafters 模板合集','license':'素材权利信息见上游','source_url':'https://github.com/MemeCrafters/meme-generator','license_url':''}
        return MemeInfoResponse(
            key=meme.key,
            template_id=catalog_entry['id'] if catalog_entry else '',
            version=catalog_entry['version'] if catalog_entry else 1,
            attribution=attribution,
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

    @lru_cache(maxsize=128)
    def thumbnail(key: str) -> bytes:
        meme = get_meme(key)
        directory = Path(__file__).parent / 'memes' / key
        example = next((directory / ('example' + ext) for ext in ['.gif', '.jpg', '.jpeg', '.png'] if (directory / ('example' + ext)).is_file()), None)
        source = example if example else meme.generate_preview()
        with Image.open(source) as image:
            image.seek(0)
            image = image.convert('RGBA')
            image.thumbnail((256, 256))
            output = BytesIO()
            image.save(output, format='PNG', optimize=True)
            return output.getvalue()

    @app.get('/memes/{key}/thumbnail')
    async def get_thumbnail(key: str):
        if key.startswith('auto_'):
            from meme_generator.features.catalog import thumbnail as declared_thumbnail
            return await run_sync(declared_thumbnail)(key)
        try:
            content = await run_sync(thumbnail)(key)
        except MemeGeneratorException as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        return Response(content=content, media_type='image/png', headers={'Cache-Control': 'public, max-age=86400'})

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
        from meme_generator.features.catalog import refresh
        refresh()
        all_keys: list[str] = []
        text_only: list[str] = []
        image_only: list[str] = []
        mixed: list[str] = []
        cards = []
        from meme_generator.features.catalog import rows
        entries = {r['key']:r for r in rows()}

        from meme_generator.features.popularity import snapshot
        popularity = snapshot()
        for meme in sorted(get_memes(), key=lambda meme: (-popularity.get(meme.key, {}).get('heat', 0), meme.key)):
            all_keys.append(meme.key)
            params = meme.params_type
            entry = entries.get(meme.key, {})
            metadata = json.loads(entry.get('metadata','{}'))
            attribution = {k:metadata.get(k,'') for k in ('author','license','source_url','license_url')}
            if not attribution['source_url']:
                attribution = {'author':'MemeCrafters 模板合集','license':'素材权利信息见上游','source_url':'https://github.com/MemeCrafters/meme-generator','license_url':''}
            cards.append({'key':meme.key, 'name':(meme.keywords or [meme.key])[0], 'keywords':meme.keywords, 'tags':sorted(meme.tags)[:6], 'template_id':entry.get('id',''), 'version':entry.get('version',1), 'featured_trial':bool(metadata.get('featured_trial')), 'attribution':attribution, 'params_type':{'min_images':params.min_images,'max_images':params.max_images,'min_texts':params.min_texts,'max_texts':params.max_texts,'default_texts':params.default_texts}, **popularity.get(meme.key, {'heat':0, 'counts':{}})})
            if params.min_images == 0 and params.max_images == 0 and params.min_texts >= 1:
                text_only.append(meme.key)
            elif params.min_texts == 0 and params.max_texts == 0 and params.min_images >= 1:
                image_only.append(meme.key)
            elif params.min_images >= 1 and params.min_texts >= 1:
                mixed.append(meme.key)

        from meme_generator.features.client_render import public_recipes
        return {
            "client": public_recipes(),
            "all": all_keys,
            "text_only": text_only,
            "image_only": image_only,
            "mixed": mixed,
            "cards": cards,
        }

    for meme in sorted(get_memes(), key=lambda meme: meme.key):
        register_router(meme)


def run_server():
    import uvicorn

    uvicorn.run(
        app,
        host=meme_config.server.host,
        port=meme_config.server.port,
        log_config=LOGGING_CONFIG,
    )


register_routers()
from meme_generator.features.catalog import router as catalog_router, bootstrap, refresh
from meme_generator.features.recommend import router as recommend_router
bootstrap()
refresh()
app.include_router(catalog_router)
app.include_router(recommend_router)
from meme_generator.features.popularity import router as popularity_router
app.include_router(popularity_router)
from meme_generator.features.client_render import router as client_render_router
app.include_router(client_render_router)


if __name__ == "__main__":
    setup_logger()
    run_server()
