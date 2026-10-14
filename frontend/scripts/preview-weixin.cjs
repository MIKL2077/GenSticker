const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawnSync}=require('node:child_process')
const root=path.resolve(__dirname,'..')
function run(command,args){const result=spawnSync(command,args,{cwd:root,stdio:'inherit',shell:false});if(result.error)throw result.error;if(result.status!==0)throw Error(`${path.basename(command)} exited with status ${result.status}`)}
try {
  run(process.platform==='win32'?'npm.cmd':'npm',['run','build:mp-weixin'])
  const source=path.join(root,'dist/build/mp-weixin'),config=JSON.parse(fs.readFileSync(path.join(source,'project.config.json'),'utf8'))
  if(config.appid!=='wx2e3a058ed0117034'||config.setting?.urlCheck!==true)throw Error('Preview requires the GenSticker AppID and enabled domain validation')
  const project=fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-weixin-preview-'))
  // Import the current build normally. Never copy stale private project settings
  // or edit DevTools' permission records; WeChat supplies the domain metadata.
  fs.cpSync(source,project,{recursive:true,filter:file=>path.basename(file)!=='project.private.config.json'})
  const args=process.argv.slice(2),index=args.indexOf('--qr-output')
  if(args.length && (index!==0 || args.length!==2 || !args[1]))throw Error('Usage: npm run preview:mp-weixin -- [--qr-output /absolute/path.png]')
  const output=index===0?path.resolve(args[1]):path.join(os.tmpdir(),`gensticker-preview-${Date.now()}.png`)
  const cli=process.env.WECHAT_DEVTOOLS_CLI_PATH||'/Applications/wechatwebdevtools.app/Contents/MacOS/cli'
  console.log('Preview project:',project)
  run(cli,['open','--project',project])
  run(cli,['preview','--project',project,'--qr-format','image','--qr-output',output])
  console.log('QR image:',output)
} catch(error){console.error(error.message);process.exitCode=1}
