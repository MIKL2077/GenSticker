export const defaultCaptionStyle=()=>({x:.5,y:.82,size:.1,color:'#ffffff',background:'none',bold:true})
export function normalizeCaptionStyle(value={}){
 const clamp=(number,min,max,fallback)=>Number.isFinite(number)?Math.max(min,Math.min(max,number)):fallback
 return {x:clamp(value.x,0,1,.5),y:clamp(value.y,0,1,.82),size:clamp(value.size,.05,.25,.1),color:/^#[0-9a-fA-F]{6}$/.test(value.color||'')?value.color:'#ffffff',background:['none','dark','light','color'].includes(value.background)?value.background:'none',bold:value.bold!==false}
}
export function paintCaption(ctx,text,width,height,value){
 const style=normalizeCaptionStyle(value),size=Math.max(8,Math.round(width*style.size)),lineHeight=Math.round(size*1.2),lines=[];let line=''
 ctx.save();ctx.font=`${style.bold?'bold ':''}${size}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top'
 for(const char of text){if(char==='\n'){lines.push(line);line='';continue}if(ctx.measureText(line+char).width>width*.9&&line){lines.push(line);line=char}else line+=char}if(line)lines.push(line)
 const visible=lines.slice(0,3),x=style.x*width,top=style.y*height-visible.length*lineHeight/2,pad=4,maxWidth=Math.max(0,...visible.map(value=>ctx.measureText(value).width))
 if(style.background!=='none'){ctx.fillStyle=({dark:'#263f48',light:'#fffaf5',color:style.color})[style.background];ctx.fillRect(x-maxWidth/2-pad,top-pad,maxWidth+pad*2,visible.length*lineHeight+pad*2)}
 ctx.fillStyle=style.background==='light'&&style.color.toLowerCase()==='#ffffff'?'#263f48':style.background==='color'?'#ffffff':style.color
 if(style.background==='none'){ctx.strokeStyle=style.color==='#263f48'?'#ffffff':'#263f48';ctx.lineWidth=Math.max(1,size*.07);ctx.lineJoin='round'}
 visible.forEach((value,index)=>{if(style.background==='none')ctx.strokeText(value,x,top+index*lineHeight);ctx.fillText(value,x,top+index*lineHeight)});ctx.restore()
}
