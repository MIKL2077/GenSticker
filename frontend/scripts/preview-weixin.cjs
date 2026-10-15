const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawnSync}=require('node:child_process')
const root=path.resolve(__dirname,'..')
function run(command,args){const result=spawnSync(command,args,{cwd:root,stdio:'inherit',shell:false});if(result.error)throw result.error;if(result.status!==0)throw Error(`${path.basename(command)} exited with status ${result.status}`)}
try {
  const args=process.argv.slice(2),openOnly=args[0]==='--open-only'
  if(openOnly)args.shift()
  if(args.length && (openOnly || args.length!==2 || args[0]!=='--qr-output' || !args[1]))throw Error('Usage: node scripts/preview-weixin.cjs [--open-only | --qr-output /absolute/path.png]')
  run(process.platform==='win32'?'npm.cmd':'npm',['run','build:mp-weixin'])
  const source=path.join(root,'dist/build/mp-weixin'),config=JSON.parse(fs.readFileSync(path.join(source,'project.config.json'),'utf8'))
  if(config.appid!=='wx2e3a058ed0117034'||config.setting?.urlCheck!==true)throw Error('Preview requires the GenSticker AppID and enabled domain validation')
  const project=fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-weixin-preview-'))
  // Import the current build normally. Never copy stale private project settings
  // or edit DevTools' permission records; WeChat supplies the domain metadata.
  fs.cpSync(source,project,{recursive:true,filter:file=>path.basename(file)!=='project.private.config.json'})
  config.projectname=`GenSticker-public-${path.basename(project).split('-').at(-1)}`
  fs.writeFileSync(path.join(project,'project.config.json'),JSON.stringify(config,null,2)+'\n')
  const output=args.length?path.resolve(args[1]):path.join(os.tmpdir(),`gensticker-preview-${Date.now()}.png`)
  const cli=process.env.WECHAT_DEVTOOLS_CLI_PATH||'/Applications/wechatwebdevtools.app/Contents/MacOS/cli'
  // Close only this repository's older generated project windows. Leaving one
  // visible makes it easy to keep testing its stale domain list by mistake.
  for(const oldProject of [source,path.join(root,'dist/dev/mp-weixin')]) {
    if(!fs.existsSync(path.join(oldProject,'project.config.json')))continue
    const closed=spawnSync(cli,['close','--project',oldProject],{cwd:root,encoding:'utf8',shell:false})
    if(closed.error || closed.status!==0)console.warn('Could not close old project window; use the new window:',oldProject)
  }
  console.log('Project window:',config.projectname)
  console.log('Preview project:',project)
  console.log('Backend: https://www.shangkun.uk/gensticker/api (domain validation enabled)')
  run(cli,['open','--project',project])
  if(!openOnly) {
    run(cli,['preview','--project',project,'--qr-format','image','--qr-output',output])
    console.log('QR image:',output)
  }
} catch(error){console.error(error.message);process.exitCode=1}
