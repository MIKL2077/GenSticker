"""Check provider configuration without exposing secrets or using a real user."""
import json,shlex
from pathlib import Path
from io import BytesIO
import httpx
from PIL import Image
values={}
for line in Path('/etc/gensticker.env').read_text().splitlines():
 key,sep,value=line.partition('=')
 if sep and key in ('WX_APPID','WX_APP_SECRET'):
  parsed=shlex.split(value);values[key]=parsed[0] if parsed else ''
report={}
try:
 with httpx.Client(timeout=20) as client:
  token=client.get('https://api.weixin.qq.com/cgi-bin/token',params={'grant_type':'client_credential','appid':values['WX_APPID'],'secret':values['WX_APP_SECRET']}).json()
  report['access_token_ready']=bool(token.get('access_token'))
  if not token.get('access_token'):report.update(code=token.get('errcode'),message=token.get('errmsg','')[:160])
  else:
   params={'access_token':token['access_token']}
   output=BytesIO();Image.new('RGB',(100,100),'white').save(output,'JPEG')
   image=client.post('https://api.weixin.qq.com/wxa/img_sec_check',params=params,files={'media':('fixture.jpg',output.getvalue(),'image/jpeg')}).json()
   report['image_api_code']=image.get('errcode');report['image_api_message']=image.get('errmsg','')[:120]
   # An invalid synthetic openid is intentional: no real user is impersonated.
   text=client.post('https://api.weixin.qq.com/wxa/msg_sec_check',params=params,json={'version':2,'scene':2,'openid':'synthetic-verification-not-a-real-user','content':'hello'}).json()
   report['text_api_code']=text.get('errcode');report['text_api_message']=text.get('errmsg','')[:120]
except Exception as error:report['transport_error']=type(error).__name__
print(json.dumps(report,ensure_ascii=False))
