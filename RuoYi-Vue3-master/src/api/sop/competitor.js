import request from '@/utils/request'

export function listEbayCompetitors(params) {
  return request({
    url: '/sop/competitor/list',
    method: 'get',
    params
  })
}

export function queryEbayCompetitor(url, options = {}) {
  return request({
    url: '/sop/competitor/query',
    method: 'post',
    data: { url },
    headers: {
      repeatSubmit: false
    },
    timeout: 60000,
    skipErrorMessage: options.silent === true
  })
}

export function importEbayCompetitorLinks(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/sop/competitor/import-links',
    method: 'post',
    data,
    headers: {
      'Content-Type': 'multipart/form-data',
      repeatSubmit: false
    },
    timeout: 60000
  })
}

export function exportEbayCompetitors(data) {
  return request({
    url: '/sop/competitor/export',
    method: 'post',
    data,
    responseType: 'blob',
    headers: {
      repeatSubmit: false
    },
    timeout: 120000
  })
}

export function saveEbayCompetitor(data) {
  return request({
    url: '/sop/competitor/save',
    method: 'post',
    data,
    headers: {
      repeatSubmit: false
    },
    timeout: 60000
  })
}

export function updateEbayCompetitor(id, data) {
  return request({
    url: `/sop/competitor/${id}`,
    method: 'put',
    data,
    headers: {
      repeatSubmit: false
    }
  })
}

export function deleteEbayCompetitor(id) {
  return request({
    url: `/sop/competitor/${id}`,
    method: 'delete'
  })
}
