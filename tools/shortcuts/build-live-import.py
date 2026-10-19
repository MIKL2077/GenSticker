"""Build our own Apple Shortcut using public Workflow action definitions.

Run `shortcuts sign --mode anyone --input /tmp/GenSticker-Live.unsigned.shortcut
--output frontend/public/GenSticker-Live.shortcut` on macOS before packaging.
No account secrets are embedded. The clipboard supplies a one-use capability.
"""
import plistlib,uuid
from pathlib import Path

def action(name,**parameters):
    identifier=str(uuid.uuid4()).upper()
    return {'WFWorkflowActionIdentifier':'is.workflow.actions.'+name,'WFWorkflowActionParameters':{'UUID':identifier,**parameters}},identifier

def value(identifier,name):return {'OutputUUID':identifier,'OutputName':name,'Type':'ActionOutput'}
def attachment(identifier,name):return {'Value':value(identifier,name),'WFSerializationType':'WFTextTokenAttachment'}
def text_variable(identifier,name):return {'Value':{'string':'\ufffc','attachmentsByRange':{'{0, 1}':value(identifier,name)}},'WFSerializationType':'WFTextTokenString'}

get_token,token=action('getclipboard')
select,photo=action('selectphoto',WFSelectMultiplePhotos=False)
encode,video=action('encodemedia',WFInput=attachment(photo,'Photos'),WFMediaAudioOnly=False,WFMediaSize='640x480',WFMediaSpeed='Normal')
headers={'Value':{'WFDictionaryFieldValueItems':[{'WFItemType':0,'WFKey':{'Value':{'string':'X-Live-Import'},'WFSerializationType':'WFTextTokenString'},'WFValue':text_variable(token,'Clipboard')}]},'WFSerializationType':'WFDictionaryFieldValue'}
send,response=action('downloadurl',WFURL='https://www.shangkun.uk/gensticker/api/studio/live/imports/receive',WFHTTPMethod='POST',WFHTTPBodyType='File',WFRequestVariable=attachment(video,'Encoded Media'),WFHTTPHeaders=headers,WFFormValues={'Value':{'WFDictionaryFieldValueItems':[]},'WFSerializationType':'WFDictionaryFieldValue'})
show,_=action('quicklook',WFInput=attachment(response,'Contents of URL'))
workflow={'WFWorkflowName':'GenSticker Live 直连','WFWorkflowClientVersion':'2600','WFWorkflowClientRelease':'6.0','WFWorkflowMinimumClientVersion':900,'WFWorkflowMinimumClientVersionString':'900','WFWorkflowTypes':[],'WFWorkflowInputContentItemClasses':['WFPhotoMediaContentItem'],'WFWorkflowIcon':{'WFWorkflowIconStartColor':4282601983,'WFWorkflowIconGlyphNumber':59511},'WFWorkflowImportQuestions':[],'WFWorkflowActions':[get_token,select,encode,send,show]}
target=Path('/tmp/GenSticker-Live.unsigned.shortcut');target.write_bytes(plistlib.dumps(workflow,fmt=plistlib.FMT_BINARY,sort_keys=False));print(target)
