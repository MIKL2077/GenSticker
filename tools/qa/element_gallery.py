"""Build a private local source/output gallery for template acceptance."""
import json
from pathlib import Path

folder=Path('artifacts/meme-rebuild').resolve()
inventory=json.loads((folder/'inventory.json').read_text())
rows=json.loads((folder/'final-drafts/index.json').read_text());data=[]
for row in rows:
    if row['status']!='draft':continue
    source=inventory[row['index']]
    data.append({'index':row['index'],'name':row['name'],'images':row['image_slots'],'texts':row['text_slots'],
                 'gif':source['frames']>1,'source':str(Path(source['path']).resolve().relative_to(folder)),
                 'output':str(Path(row['draft_output']).resolve().relative_to(folder))})
page='''<!doctype html><meta charset="utf-8"><title>GenSticker 原图元素替换验收</title>
<style>body{font:16px system-ui;background:#edf2f4;color:#17323d;margin:24px}header{position:sticky;top:0;background:#edf2f4ee;padding:10px;z-index:1}h1{font-size:24px}input,select{font:inherit;padding:8px;border:1px solid #aaa;border-radius:8px}#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}article{background:white;border-radius:14px;padding:14px}h2{font-size:16px}figure{margin:0;display:flex;gap:8px}figure div{width:50%}img{width:100%;height:210px;object-fit:contain;background:#f6f7f8}small{color:#59707f}</style>
<header><h1>原图元素替换 · 本机验收样本</h1><p>左侧原素材，右侧使用测试头像与“新文案”的实际生成结果。GIF 直接播放。</p><input id="query" placeholder="搜索名称或编号"> <select id="kind"><option value="">全部</option><option>头像</option><option>原字</option><option>图文</option></select> <label><input id="motion" type="checkbox">只看 GIF</label><p id="count"></p></header><main id="grid"></main>
<script>const data=__DATA__;function draw(){const q=document.querySelector('#query').value,kind=document.querySelector('#kind').value,gif=document.querySelector('#motion').checked;const rows=data.filter(r=>(!q||r.name.includes(q)||String(r.index).includes(q))&&(!gif||r.gif)&&(!kind||kind===(r.images?(r.texts?'图文':'头像'):'原字')));document.querySelector('#count').textContent=rows.length+' / '+data.length+' 个通过检查的模板';const grid=document.querySelector('#grid');grid.replaceChildren();for(const r of rows){const card=document.createElement('article'),title=document.createElement('h2'),pair=document.createElement('figure'),hint=document.createElement('p');title.textContent=r.index+' · '+r.name+(r.gif?' · GIF':'');for(const [label,path]of [['原素材',r.source],['实际替换',r.output]]){const wrap=document.createElement('div'),img=document.createElement('img'),small=document.createElement('small');img.src=path;img.loading='lazy';small.textContent=label;wrap.append(img,small);pair.append(wrap)}hint.textContent=r.images+' 个头像 / '+r.texts+' 个原字字段';card.append(title,pair,hint);grid.append(card)}}for(const id of ['query','kind','motion'])document.getElementById(id).addEventListener('input',draw);draw();</script>'''
(folder/'acceptance.html').write_text(page.replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('<','\\u003c')))
print('Private local acceptance gallery:',len(data))
