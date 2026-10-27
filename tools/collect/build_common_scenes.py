"""Build licensed OpenMoji chat reactions with editable wording (offline only)."""
import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path
import urllib.request
from PIL import Image, ImageOps, ImageDraw

SCENES=[
    ('happy','开心到起飞','1F604','今天超开心',['开心','快乐','高兴','哈哈','欢乐']),
    ('goodnight','晚安好梦','1F634','晚安，好梦',['晚安','睡觉','困了','好梦','睡了']),
    ('hello','你好呀','1F44B','你好呀',['你好','嗨','哈喽','打招呼','问好']),
    ('thanks','谢谢你呀','1F64F','谢谢你呀',['谢谢','感谢','多谢','感恩','辛苦了']),
    ('morning','早安打卡','1F305','早上好',['早安','早上好','起床','打卡']),
    ('bye','挥手拜拜','1F44B','拜拜，下次聊',['再见','拜拜','告别','回头见']),
    ('okay','收到没问题','1F44C','收到，没问题',['好的','收到','明白','没问题','OK']),
    ('sorry','抱歉啦','1F647','对不起啦',['对不起','抱歉','不好意思','道歉']),
    ('cheer','给你加油','1F4AA','加油，你可以',['加油','努力','冲鸭','鼓励','支持']),
    ('love','比个心给你','1F970','爱你哟',['爱你','比心','喜欢','亲亲','心动']),
    ('food','干饭时间到','1F60B','该吃饭啦',['吃饭','干饭','饿了','美食']),
    ('work','打工人续命','2615','喝口再干',['上班','打工','工作','摸鱼','咖啡']),
]


def main():
    project=Path(__file__).resolve().parents[2]
    from meme_generator.features.declarative import render, font
    from meme_generator.features.store import root
    templates=[];assets={};images={}
    def asset(image):
        out=BytesIO();image.save(out,'PNG',optimize=True);raw=out.getvalue()
        digest=hashlib.sha256(raw).hexdigest();assets[digest]=base64.b64encode(raw).decode()
        directory=root()/'template_assets';directory.mkdir(exist_ok=True);(directory/(digest+'.png')).write_bytes(raw)
        return digest
    sheet=Image.new('RGB',(4*320,3*360),'#f7f4ee')
    for i,(key,name,code,caption,words) in enumerate(SCENES):
        if code not in images:
            url=f'https://raw.githubusercontent.com/hfg-gmuend/openmoji/15.1.0/color/618x618/{code}.png'
            with urllib.request.urlopen(url,timeout=20) as response:raw=response.read(1024*1024)
            images[code]=Image.open(BytesIO(raw)).convert('RGBA')
        symbol=ImageOps.contain(images[code],(270,270),Image.Resampling.LANCZOS)
        plate=Image.new('RGBA',(400,400),'#fffaf0');plate.alpha_composite(symbol,((400-symbol.width)//2,10))
        # The symbol is the reaction itself; the entire caption remains editable.
        digest=asset(plate)
        spec={'width':400,'height':400,'background':'#fffaf0','defaults':[caption],
              'layers':[{'type':'asset','box':[0,0,400,400],'value':digest},
                        {'type':'text','slot':0,'box':[20,302,360,76],'value':caption,'font_size':50,'weight':'bold','align':'center','color':'#273c43','max_lines':2}]}
        metadata={'name':name,'keywords':words,'tags':words[:3], 'min_images':0,'max_images':0,'min_texts':1,'max_texts':1,'default_texts':[caption],
                  'origin':'openmoji','author':'OpenMoji contributors / HfG Schwäbisch Gmünd','license':'CC BY-SA 4.0','license_url':'https://creativecommons.org/licenses/by-sa/4.0/',
                  'source_url':f'https://github.com/hfg-gmuend/openmoji/blob/15.1.0/color/618x618/{code}.png',
                  'source_revision':'15.1.0','changes':'Resized OpenMoji symbol on an original editable Chinese chat reaction layout; CC BY-SA 4.0',
                  'input_hint':'原表情保留，可修改整句文字。','created_at':1793059200,'animated':False}
        template={'key':'auto_scene_'+key,'version':1,'metadata':metadata,'spec':spec};templates.append(template)
        with Image.open(render(spec,[],[caption])) as image:sheet.paste(image.resize((320,320)),((i%4)*320,(i//4)*360))
        # Actual edited and cleared captions exercise the complete text slot.
        render(spec,[],['收到啦']);render(spec,[],['第一行\n第二行']);render(spec,[],[''])
    destination=project/'backend/meme-generator/meme_generator/features/common_scenes.json'
    destination.write_text(json.dumps({'templates':templates,'assets':assets},ensure_ascii=False,separators=(',',':')))
    review=project/'artifacts/fusion-loading-20261027';review.mkdir(parents=True,exist_ok=True);sheet.save(review/'common-scenes.jpg',quality=93)
    print('Prepared',len(templates),'templates;',len(assets),'hashed assets;',destination.stat().st_size,'bytes')


if __name__=='__main__':main()
