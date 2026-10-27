from meme_generator.safe_images import open_image
import json
import base64
import binascii
import asyncio
import hashlib
import time
import threading
from contextlib import asynccontextmanager, suppress
from functools import lru_cache
from io import BytesIO
from datetime import datetime
from typing import Any, Literal, Optional
from pathlib import Path

import filetype
from PIL import Image
from fastapi.responses import JSONResponse
from fastapi import Depends, FastAPI, Form, File, HTTPException, Response, UploadFile, Request
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
from meme_generator.features.search_terms import keywords as search_keywords

@asynccontextmanager
async def lifespan(app):
    async def expire_private_cache():
        while True:
            await asyncio.sleep(30)
            render_cache.prune()
            subject_cache.prune()
    from meme_generator.features.subjects import warm_subject_model
    async def warm_foreground():
        try:
            await run_sync(warm_subject_model)()
        except Exception:
            import logging
            logging.getLogger(__name__).warning('foreground model warmup unavailable; retry on demand')
    warm_task = asyncio.create_task(warm_foreground())
    task = asyncio.create_task(expire_private_cache())
    try:
        yield
    finally:
        warm_task.cancel()
        with suppress(asyncio.CancelledError):
            await warm_task
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        render_cache.items.clear()
        render_cache.bytes = 0
        subject_cache.items.clear();subject_cache.bytes=0


app = FastAPI(lifespan=lifespan)
from meme_generator.features.traffic import TrafficBudget
app.add_middleware(TrafficBudget)
from meme_generator.features.moderation import AvailabilityGuard
app.add_middleware(AvailabilityGuard)
app.include_router(account_router)
from meme_generator.features.share import router as share_router
app.include_router(share_router)
generation_slots = asyncio.Semaphore(2)
from meme_generator.features.render_cache import RenderCache
render_cache = RenderCache()
subject_cache = RenderCache(max_entries=8)
_subject_locks = [threading.RLock() for _ in range(16)]

def subject_key(identity, raw, variant='subject'):
    return hashlib.sha256(identity.encode()+b'\0u2netp-subject-v1\0'+(b'mask\0' if variant=='mask' else b'')+raw).hexdigest()

def prepare_subject_mask(raw,identity):
    from meme_generator.features.subjects import extract_subject_mask
    key=subject_key(identity,raw,'mask')
    with _subject_locks[int(key[:2],16)%len(_subject_locks)]:
        value=subject_cache.get(key)
        if value is None:
            value=extract_subject_mask(raw);subject_cache.put(key,value)
    return value

def prepare_inputs(images, identity):
    from meme_generator.features.subjects import extract_subject
    output=[]
    for raw in images:
        key=subject_key(identity,raw)
        with _subject_locks[int(key[:2],16)%len(_subject_locks)]:
            value=subject_cache.get(key)
            if value is None:
                value=extract_subject(raw);subject_cache.put(key,value)
        output.append(value)
    return output


class GenerateRequest(BaseModel):
    images: list[str] = Field(default_factory=list, max_length=10)
    texts: list[str] = Field(default_factory=list, max_length=20)
    args: dict[str, Any] = Field(default_factory=dict,max_length=32)
    extract_subject: bool = Field(default=False,strict=True)


@app.get('/healthz')
def healthz():
    return {'status': 'ok', 'templates': len(get_meme_keys())}


class SubjectPreviewRequest(BaseModel):
    image: str = Field(min_length=1, max_length=12 * 1024 * 1024)
    delivery: str = "binary"


@app.post('/images/subject')
async def subject_preview(params: SubjectPreviewRequest, request: Request):
    """Private foreground preview; shares inference slots/cache with generation."""
    from meme_generator.features.popularity import actor
    from PIL import UnidentifiedImageError
    try:
        raw = base64.b64decode(params.image, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=422, detail='图片格式无效，请重新选择')
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='图片过大，先缩小后再试')
    started=time.perf_counter()
    identity=actor(request)
    content=subject_cache.get(subject_key(identity,raw,'mask' if params.delivery=='mask' else 'subject'))
    cached=content is not None
    if not cached:
        if generation_slots.locked():
            raise HTTPException(status_code=503, detail='图片处理繁忙，请稍后再试')
        async with generation_slots:
            try:
                content = await run_sync(prepare_subject_mask)(raw,identity) if params.delivery=='mask' else (await run_sync(prepare_inputs)([raw], identity))[0]
            except MemeGeneratorException as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.message)
            except (UnidentifiedImageError, Image.DecompressionBombError, ValueError, OSError):
                raise HTTPException(status_code=422, detail='图片无法读取，请选择静态图片')
    headers={'Cache-Control':'private, no-store','X-Gensticker-Cache':'hit' if cached else 'miss','Server-Timing':f'foreground;dur={(time.perf_counter()-started)*1000:.1f}'}
    if params.delivery=='mask':
        return JSONResponse({'mask':base64.b64encode(content).decode(),'width':320,'height':320},headers=headers)
    if params.delivery=='url':
        from meme_generator.features.editor import deliver_foreground
        return JSONResponse(deliver_foreground(content,request),headers=headers)
    return Response(content=content, media_type='image/png', headers=headers)


@app.post('/images/subject-file')
async def subject_file(request:Request,file:UploadFile=File(...),delivery:Literal['url','mask']=Form('url')):
    """Use native WeChat multipart upload and a private PNG download ticket."""
    raw=await file.read(8*1024*1024+1)
    if not raw:raise HTTPException(422,'图片为空，请重新选择')
    if len(raw)>8*1024*1024:raise HTTPException(413,'图片过大，先缩小后再试')
    return await subject_preview(SubjectPreviewRequest(image=base64.b64encode(raw).decode(),delivery=delivery),request)


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
    if len(json.dumps(params.args).encode())>32768:raise HTTPException(413,'模板参数过大，请减少参数后重试')
    args_model = meme.params_type.args_type.args_model if meme.params_type.args_type else MemeArgsModel
    try:
        args = type_validate_python(args_model, params.args)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    from meme_generator.features.popularity import record, actor
    identity = actor(request)
    cache_key = hashlib.sha256(json.dumps([identity, key, loaded_versions.get(key, 1), params.images, params.texts, model_dump(args),params.extract_subject],sort_keys=True).encode()).hexdigest()
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
            if params.extract_subject:images=await run_sync(prepare_inputs)(images,identity)
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
    face_blend: bool = False
    template_id: str = ''
    version: int = 1
    input_hint: str = ''
    attribution: dict[str,str] = Field(default_factory=dict)
    creator: dict = Field(default_factory=dict)
    created_at: float = 0
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
        extract_subject: bool = Form(default=False),
    ):
        imgs: list[bytes] = []
        for image in images:
            raw = await image.read(10 * 1024 * 1024 + 1)
            if len(raw) > 10 * 1024 * 1024 or sum(map(len, imgs)) + len(raw) > 10 * 1024 * 1024:
                raise HTTPException(413, '图片总大小不能超过 10 MB')
            imgs.append(raw)

        texts = [text for text in texts if text]

        assert isinstance(args, args_model)

        try:
            from meme_generator.features.catalog import refresh
            refresh();get_meme(meme.key)
            if generation_slots.locked():raise HTTPException(503,'生成队列已满，请稍后重试')
            async with generation_slots:
                if extract_subject:
                    from meme_generator.features.popularity import actor
                    imgs=await run_sync(prepare_inputs)(imgs,actor(request))
                result = await run_sync(meme)(images=imgs,texts=texts,args=model_dump(args))
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
        try: catalog_entry=db.execute('SELECT id,version,metadata,spec FROM templates WHERE key=?',(key,)).fetchone()
        finally: db.close()
        attribution={k:json.loads(catalog_entry['metadata']).get(k,'') for k in ['author','license','source_url','license_url']} if catalog_entry else {}
        if not attribution.get('source_url'):
            attribution={'author':'MemeCrafters 模板合集','license':'素材权利信息见上游','source_url':'https://github.com/MemeCrafters/meme-generator','license_url':''}
        return MemeInfoResponse(
            key=meme.key,
            face_blend=bool(catalog_entry and catalog_entry['spec'] and '"face"' in catalog_entry['spec']),
            template_id=catalog_entry['id'] if catalog_entry else '',
            version=catalog_entry['version'] if catalog_entry else 1,
            input_hint=json.loads(catalog_entry['metadata']).get('input_hint','') if catalog_entry else '',
            attribution=attribution,
            creator=json.loads(catalog_entry['metadata']).get('creator',{}) if catalog_entry else {},
            created_at=json.loads(catalog_entry['metadata']).get('created_at',0) if catalog_entry else 0,
            params_type=MemeParamsResponse(
                min_images=meme.params_type.min_images,
                max_images=meme.params_type.max_images,
                min_texts=meme.params_type.min_texts,
                max_texts=meme.params_type.max_texts,
                default_texts=meme.params_type.default_texts,
                args_type=args_type_response,
            ),
            keywords=search_keywords({**(json.loads(catalog_entry['metadata']) if catalog_entry else {}),'name':(meme.keywords or [meme.key])[0]},meme.keywords),
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

    @app.get('/memes/{key}/thumbnail')
    async def get_thumbnail(key: str, v: str | None = None):
        from meme_generator.features.catalog import refresh, declared
        from meme_generator.features.public_preview import response, declared_source
        try:
            row=declared(key)
        except HTTPException:
            if key.startswith('auto_'):raise
            refresh()
            try:meme=get_meme(key)
            except MemeGeneratorException as e:raise HTTPException(e.status_code,e.message)
            directory=Path(__file__).parent/'memes'/key
            example=next((directory/('example'+ext) for ext in ['.gif','.jpg','.jpeg','.png'] if (directory/('example'+ext)).is_file()),None)
            from meme_generator.features.client_render import version
            return await run_sync(response)(key,version(key),lambda: example or meme.generate_preview(),v)
        return await run_sync(response)(key,row['version'],lambda:declared_source(row),v)

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
    def _(compact: bool = False):
        """按输入需求对表情进行分类并返回各分类的 key 列表。
        
        分类规则（基于支持的输入类型，含可选文字）：
        - 仅文字: max_images == 0 且 max_texts > 0
        - 仅图片: max_texts == 0 且 max_images > 0
        - 图文混合: max_images > 0 且 max_texts > 0
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
            cards.append({'key':meme.key, 'name':(meme.keywords or [meme.key])[0], 'animated':bool(metadata.get('animated')), 'keywords':search_keywords({**metadata,'name':(meme.keywords or [meme.key])[0]},meme.keywords), 'face_blend':bool(entry.get('spec') and '"face"' in entry['spec']), 'tags':sorted(meme.tags)[:6], 'template_id':entry.get('id',''), 'version':entry.get('version',1), 'creator':metadata.get('creator',{}),'created_at':metadata.get('created_at',0),'featured_trial':bool(metadata.get('featured_trial')), 'input_hint':metadata.get('input_hint',''), 'attribution':attribution, 'params_type':{'min_images':params.min_images,'max_images':params.max_images,'min_texts':params.min_texts,'max_texts':params.max_texts,'default_texts':params.default_texts}, **popularity.get(meme.key, {'heat':0, 'counts':{}})})
            if params.max_images == 0 and params.max_texts > 0:
                text_only.append(meme.key)
            elif params.max_texts == 0 and params.max_images > 0:
                image_only.append(meme.key)
            elif params.max_images > 0 and params.max_texts > 0:
                mixed.append(meme.key)

        if compact:
            for card in cards:
                for name in ('attribution','counts','creator','featured_trial'):
                    card.pop(name,None)
        from meme_generator.features.client_render import public_recipes
        return {
            "client": {} if compact else public_recipes(),
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
from meme_generator.features.trials import router as trials_router
app.include_router(trials_router)
app.include_router(recommend_router)
from meme_generator.features.popularity import router as popularity_router
app.include_router(popularity_router)
from meme_generator.features.client_render import router as client_render_router
app.include_router(client_render_router)
from meme_generator.features.studio import router as studio_router
app.include_router(studio_router)
from meme_generator.features.editor import router as editor_router
app.include_router(editor_router)
from meme_generator.features.subject_model import router as subject_model_router
app.include_router(subject_model_router)
from meme_generator.features.livegif import router as live_router
app.include_router(live_router)
from meme_generator.features.lifecycle import router as lifecycle_router
app.include_router(lifecycle_router)
from meme_generator.features.export import router as export_router
app.include_router(export_router)


@app.post('/memes/{key}/')
async def generate_dynamic_multipart(key: str, request: Request, images: list[UploadFile] = [], texts: list[str] = Form(default=[]), args: str = Form(default='{}'), extract_subject: bool = Form(default=False)):
    # Published user templates are loaded after startup and share the existing renderer.
    encoded=[];total=0
    for image in images:
        raw=await image.read(10*1024*1024+1);total+=len(raw)
        if total>10*1024*1024:raise HTTPException(413,'图片总大小不能超过 10 MB')
        encoded.append(base64.b64encode(raw).decode())
    try:options=json.loads(args)
    except (ValueError,TypeError):raise HTTPException(422,'模板参数必须是 JSON 对象')
    if not isinstance(options,dict):raise HTTPException(422,'模板参数必须是 JSON 对象')
    return await generate_json(key,GenerateRequest(images=encoded,texts=texts,args=options,extract_subject=extract_subject),request)


if __name__ == "__main__":
    setup_logger()
    run_server()
