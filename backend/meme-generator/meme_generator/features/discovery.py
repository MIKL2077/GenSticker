"""Discover candidate metadata without assuming a site's images are licensed."""
import hashlib
import json
import subprocess
import time
from urllib.parse import quote
from .store import connect
from .recommend import day

SOURCES = [
    {'id':'chinesebqb','name':'ChineseBQB','url':'https://github.com/zhaoolee/ChineseBQB/tree/master','mode':'metadata-discovery','license_status':'per-image-unverified','reason':'仓库代码许可不代表每张图片的改编与再分发许可'},
    {'id':'aigei','name':'爱给表情素材','url':'https://www.aigei.com/lib/sticker/','mode':'registered','license_status':'per-item-required','reason':'按素材页面区分 CC、版权购买与其他条件；当前页面访问不可用'},
    {'id':'weshine','name':'闪萌','url':'https://u.weshineapp.com/','mode':'registered','license_status':'per-image-unverified','reason':'搜索第三方和用户上传内容需具体权利信息；当前页面访问不可用'},
]


def fetch_json(path):
    if '..' in path or not path.startswith('/repos/zhaoolee/ChineseBQB/contents'):
        raise ValueError('untrusted metadata endpoint')
    db=connect();cap=512*1024
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO budgets(day) VALUES(?)',(day(),))
            used=db.execute('SELECT bytes FROM budgets WHERE day=?',(day(),)).fetchone()[0]
            monthly=db.execute('SELECT COALESCE(SUM(bytes),0) FROM budgets WHERE day LIKE ?',(day()[:7]+'%',)).fetchone()[0]
            if used+cap>200*1024*1024 or monthly+cap>1024*1024*1024:raise ValueError('metadata budget exhausted')
            db.execute('UPDATE budgets SET bytes=bytes+? WHERE day=?',(cap,day()))
        response=subprocess.run(['curl','-4','--fail','--silent','--show-error','--connect-timeout','3','--max-time','12','--max-filesize',str(cap),'--proto','=https','-H','Accept: application/vnd.github+json','-H','User-Agent: GenSticker-licensed-discovery','https://api.github.com'+path],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,check=True)
        if len(response.stdout)>cap:raise ValueError('metadata too large')
        payload=json.loads(response.stdout)
        if not isinstance(payload,list):raise ValueError('unexpected metadata')
        with db:db.execute('UPDATE budgets SET bytes=bytes-?+? WHERE day=?',(cap,len(response.stdout),day()))
        return payload
    finally:db.close()


def discover(limit=20):
    # Interest is a discovery heuristic, not a promise of semantic humor.
    markers=('猫','狗','熊猫','程序员','沙雕','滑稽','打工','日常','小人')
    listing=fetch_json('/repos/zhaoolee/ChineseBQB/contents')
    folders=[x for x in listing if x.get('type')=='dir' and 'BQB' in x.get('name','')]
    folders.sort(key=lambda x:(-sum(t in x['name'] for t in markers),x['name']))
    preferred=[x for x in folders if any(t in x['name'] for t in markers)] or folders
    if not preferred:return {'discovered':0,'status':'no-candidates'}
    folder=preferred[int(time.time()//21600)%len(preferred)]
    path=str(folder.get('path',''))
    if not path or len(path)>200 or '/' in path:raise ValueError('invalid folder')
    items=fetch_json('/repos/zhaoolee/ChineseBQB/contents/'+quote(path,safe=''))
    files=[x for x in items if x.get('type')=='file' and str(x.get('name','')).lower().endswith(('.png','.jpg','.jpeg')) and int(x.get('size',0))<=2*1024*1024]
    files.sort(key=lambda x:hashlib.sha256((day()+x['name']).encode()).hexdigest())
    db=connect();count=0
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            remaining=max(0,100-db.execute('SELECT candidates FROM budgets WHERE day=?',(day(),)).fetchone()[0])
            for item in files[:min(limit,remaining)]:
                file_path=str(item.get('path',''))
                if not file_path.startswith(path+'/') or len(file_path)>500:continue
                source='https://github.com/zhaoolee/ChineseBQB/blob/master/'+quote(file_path,safe='/')
                reason=json.dumps({'source':'ChineseBQB','category':path,'file':item['name'],'intent_gate':'not-evaluated','license':'unverified','note':'只登记元数据，未下载素材，许可明确后才进入转换'},ensure_ascii=False)
                cursor=db.execute('INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?)',(hashlib.sha256(source.encode()).hexdigest(),source,'license-pending',reason,time.time()))
                count+=cursor.rowcount
            db.execute('UPDATE budgets SET candidates=candidates+? WHERE day=?',(count,day()))
        return {'discovered':count,'category':path,'status':'license-pending','images_downloaded':0}
    finally:db.close()
