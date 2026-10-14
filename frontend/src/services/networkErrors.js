export function requestError(error) {
  if(error instanceof Error && error.code)return error
  const raw=String(error?.errMsg || error?.message || '网络连接失败')
  const result=new Error(raw)
  result.statusCode=error?.statusCode
  if(/not in domain list|domain.*not.*allowed|域名.*(非法|未配置|不合法)/i.test(raw)) {
    result.code='DOMAIN_NOT_ALLOWED'
    result.message='当前小程序版本尚未开通服务域名，请联系开发者处理'
    result.retryable=false
  } else if(/timeout|超时/i.test(raw)) {
    result.code='NETWORK_TIMEOUT'
    result.message='连接模板服务超时，请切换网络后重试'
  } else if(/ERR_NAME_NOT_RESOLVED|dns/i.test(raw)) {
    result.code='DNS_ERROR'
    result.message='服务域名解析失败，请切换网络后重试'
  } else if(/ssl|certificate|ERR_CERT|tls/i.test(raw)) {
    result.code='TLS_ERROR'
    result.message='安全连接失败，请检查网络或联系开发者'
  } else if(result.statusCode===403) {
    result.code='ACCESS_DENIED'
    result.message='服务入口拒绝访问，请联系开发者处理'
    result.retryable=false
  } else {
    result.code=result.statusCode ? `HTTP_${result.statusCode}` : 'NETWORK_ERROR'
    if(!result.statusCode)result.message='无法连接模板服务，请切换网络后重试'
  }
  return result
}
