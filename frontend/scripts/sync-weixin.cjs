// Sync a build into an already imported project without changing WeChat privacy settings.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto')
const build=path.resolve(__dirname,'../dist/build/mp-weixin'),target=process.argv[2]
if(!target||!path.isAbsolute(target))throw Error('Pass the absolute path of the existing DevTools project')
const sourceConfig=JSON.parse(fs.readFileSync(path.join(build,'project.config.json'))),projectPath=path.join(target,'project.config.json'),project=JSON.parse(fs.readFileSync(projectPath))
const appid=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../src/manifest.json')))['mp-weixin'].appid
if(sourceConfig.appid!==appid||project.appid!==appid||appid!=='wx2e3a058ed0117034')throw Error('AppID mismatch; refusing to replace another project')
let count=0
function copy(directory,relative=''){
 for(const entry of fs.readdirSync(directory,{withFileTypes:true})){
  if(['project.config.json','project.private.config.json','.DS_Store'].includes(entry.name))continue
  const name=path.join(relative,entry.name),src=path.join(directory,entry.name),dest=path.join(target,name)
  if(entry.isSymbolicLink())throw Error('Unexpected symlink in build')
  if(entry.isDirectory()){fs.mkdirSync(dest,{recursive:true});copy(src,name)}else{fs.copyFileSync(src,dest);if(crypto.createHash('sha256').update(fs.readFileSync(src)).digest('hex')!==crypto.createHash('sha256').update(fs.readFileSync(dest)).digest('hex'))throw Error('Copy mismatch: '+name);count++}
 }
}
copy(build)
project.setting={...project.setting,...sourceConfig.setting,urlCheck:true,es6:true,enhance:true}
fs.writeFileSync(projectPath,JSON.stringify(project,null,2)+'\n')
console.log(JSON.stringify({project:target,appid,filesVerified:count,domainValidation:true},null,2))
