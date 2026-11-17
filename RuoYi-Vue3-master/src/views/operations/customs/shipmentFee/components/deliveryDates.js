let nextRowId = 0

export function deliveryRow() {
  return { id: ++nextRowId, inboundPlanId: '', shipmentNo: '', sid: '', status: 'PENDING', error: '', result: null }
}

export function clearDeliveryResult(row) {
  Object.assign(row, { status: 'PENDING', error: '', result: null })
}

export function deliveryRequest(row) {
  const inboundPlanId = String(row.inboundPlanId || '').trim()
  const shipmentNo = String(row.shipmentNo || '').trim()
  const sid = String(row.sid || '').trim()
  if (!inboundPlanId) throw new Error('请填写STA任务编号')
  if (!shipmentNo) throw new Error('请填写货件单号')
  if (inboundPlanId.length > 128 || shipmentNo.length > 128) throw new Error('STA任务编号和货件单号不能超过128个字符')
  if (!/^[0-9]+$/.test(sid) || BigInt(sid) <= 0n || BigInt(sid) > 9223372036854775807n) throw new Error('SID必须为有效的正整数')
  return { inboundPlanId, shipmentNo, sid }
}

export async function queryDeliveryRows(rows, query, isCurrent = () => true) {
  // 逐行查询；单行参数或接口失败继续后面的货件，关闭弹窗后不再发后续请求。
  for (const row of rows) {
    if (!isCurrent()) break
    clearDeliveryResult(row)
    try {
      const request = deliveryRequest(row)
      row.status = 'QUERYING'
      const result = await query(request)
      if (!isCurrent()) break
      row.result = result
      row.status = result?.success ? 'SUCCESS' : 'ERROR'
      row.error = result?.success ? '' : result?.message || '查询失败，请检查接口返回'
    } catch (error) {
      if (!isCurrent()) break
      row.status = 'ERROR'
      row.error = error?.message || '查询失败，请稍后重试'
    }
  }
}
