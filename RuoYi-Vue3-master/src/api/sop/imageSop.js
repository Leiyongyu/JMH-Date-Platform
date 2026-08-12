import request from '@/utils/request'

// 签发仅能访问图片SOP代理的临时会话，避免在浏览器暴露Python内部令牌。
export function createImageSopSession() {
  return request({
    url: '/sop/image-sop/session',
    method: 'post',
    headers: { repeatSubmit: false }
  })
}
