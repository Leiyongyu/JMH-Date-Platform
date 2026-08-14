import request from '@/utils/request'

export function createAmazonImageUploadSession() {
  return request({
    url: '/sop/script-tools/amazon-image-upload/session',
    method: 'post'
  })
}

export function getAmazonImageUploadConfig() {
  return request({
    url: '/sop/script-tools/amazon-image-upload/config',
    method: 'get'
  })
}

export function saveAmazonImageUploadConfig(data) {
  return request({
    url: '/sop/script-tools/amazon-image-upload/config',
    method: 'put',
    data
  })
}

export function clearAmazonImageUploadPassword() {
  return request({
    url: '/sop/script-tools/amazon-image-upload/config/password',
    method: 'delete'
  })
}
