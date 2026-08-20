import request from '@/utils/request'

// Java 根据当前 ERP 登录用户签发 Python 工作台工具清单和作用域会话。
export function createPythonToolsSession() {
  return request({
    url: '/sop/python-tools/session',
    method: 'post',
    headers: { repeatSubmit: false }
  })
}
