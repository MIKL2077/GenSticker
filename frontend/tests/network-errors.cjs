const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const read=p=>fs.readFileSync(path.join(__dirname,'../src/services',p),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
async function verify(){
  let calls=0;const c={Error,String,console,API_BASE_URL:'https://public.test/api',setTimeout:fn=>fn(),uni:{getStorageSync:()=>null,request:async()=>{calls++;throw {errMsg:'request:fail url not in domain list'}}}}
  vm.createContext(c);vm.runInContext(read('networkErrors.js'),c);vm.runInContext(read('apiService.js'),c)
  await assert.rejects(c.apiRequest('/memes/categories'),e=>e.code==='DOMAIN_NOT_ALLOWED' && /服务域名/.test(e.message));assert.equal(calls,1)
  c.uni.request=async()=>({statusCode:403,data:'error code: 1010'})
  await assert.rejects(c.apiRequest('/memes/categories'),e=>e.code==='ACCESS_DENIED')
  c.uni.request=async()=>{throw {errMsg:'request:fail timeout'}}
  await assert.rejects(c.apiRequest('/memes/categories',{},1),e=>e.code==='NETWORK_TIMEOUT')
  await assert.rejects(c.apiRequest('/studio/jobs',{method:'POST',timeoutMessage:'图片上传超时，请重试'},1),e=>e.code==='NETWORK_TIMEOUT'&&e.message==='图片上传超时，请重试')
  assert.equal(c.requestError({errMsg:'request:fail ssl hand shake error'}).code,'TLS_ERROR')
  assert.equal(c.requestError({errMsg:'request:fail net::ERR_CERT_AUTHORITY_INVALID'}).code,'TLS_ERROR')
  assert.equal(c.requestError({errMsg:'request:fail net::ERR_NAME_NOT_RESOLVED'}).code,'DNS_ERROR')
  c.uni.request=async()=>({statusCode:429,data:{detail:'请稍后再试'},header:{'Retry-After':'47'}})
  await assert.rejects(c.apiRequest('/recommend/jobs',{method:'POST'},3),e=>e.statusCode===429 && e.retryAfter===47)
  c.uni.request=async()=>({statusCode:200,data:{all:['one']}});assert.deepEqual(JSON.parse(JSON.stringify(await c.apiRequest('/memes/categories'))),{all:['one']})
  console.log('PASS domain failure stops retries, gateway denial, timeout, TLS diagnostics and successful requests')
}
verify().catch(e=>{console.error(e);process.exitCode=1})
