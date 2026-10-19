"""Normalized caption placement shared by video edit payloads and Pillow output."""
from typing import Literal
from pydantic import BaseModel,Field
from PIL import ImageDraw
from .declarative import font
class CaptionStyle(BaseModel):
    x:float=Field(default=.5,ge=0,le=1,allow_inf_nan=False)
    y:float=Field(default=.82,ge=0,le=1,allow_inf_nan=False)
    size:float=Field(default=.1,ge=.05,le=.25,allow_inf_nan=False)
    color:str=Field(default='#ffffff',pattern=r'^#[0-9a-fA-F]{6}$')
    background:Literal['none','dark','light','color']='none'
    bold:bool=True

def paint_caption(image,text,style):
    if not text:return
    style=CaptionStyle.model_validate(style) if isinstance(style,dict) else style
    painter=ImageDraw.Draw(image);size=max(8,round(image.width*style.size));face=font(size,style.bold);line_height=round(size*1.2);lines=[];line=''
    for char in text:
        if char=='\n':lines.append(line);line='';continue
        if painter.textlength(line+char,font=face)>image.width*.9 and line:lines.append(line);line=char
        else:line+=char
    if line:lines.append(line)
    lines=lines[:3];x=style.x*image.width;top=style.y*image.height-len(lines)*line_height/2
    width=max([painter.textlength(value,font=face) for value in lines] or [0])
    if style.background!='none':painter.rectangle((x-width/2-4,top-4,x+width/2+4,top+len(lines)*line_height+4),fill={'dark':'#263f48','light':'#fffaf5','color':style.color}[style.background])
    color='#263f48' if style.background=='light' and style.color.lower()=='#ffffff' else '#ffffff' if style.background=='color' else style.color
    for index,line in enumerate(lines):painter.text((x,top+index*line_height),line,font=face,fill=color,anchor='mt',stroke_width=max(1,round(size*.07)) if style.background=='none' else 0,stroke_fill='#ffffff' if style.color=='#263f48' else '#263f48')
