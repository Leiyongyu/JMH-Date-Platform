package com.ruoyi.system.service.operation.external.goodcang;

import com.ruoyi.system.domain.operation.external.GoodcangGrnDetail;
import com.ruoyi.system.domain.operation.external.GoodcangGrnList;
import com.ruoyi.system.mapper.operation.external.GoodcangGrnDetailMapper;
import com.ruoyi.system.mapper.operation.external.GoodcangGrnListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 谷仓入库单同步: grn_list + grn_detail */
@Service
public class GoodcangGrnSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(GoodcangGrnSyncService.class);
    private static final DateTimeFormatter DT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private final GoodcangClient client;
    private final GoodcangGrnListMapper listMapper;
    private final GoodcangGrnDetailMapper detailMapper;

    public GoodcangGrnSyncService(GoodcangClient c, GoodcangGrnListMapper l, GoodcangGrnDetailMapper d)
    { this.client = c; this.listMapper = l; this.detailMapper = d; }

    /** 校准模式：不传时间拉全量入库单 */
    public OperationSyncResult syncGrnListAll() throws Exception
    {
        long start = System.currentTimeMillis();
        int total = 0, page = 1;
        while (true)
        {
            Map<String, Object> resp = client.getGrnListAll(page, 200);
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> data = (List<Map<String, Object>>) resp.get("data");
            if (data == null || data.isEmpty()) break;
            for (Map<String, Object> item : data)
            {
                String code = str(item, "receiving_code");
                if (code == null || code.isEmpty()) continue;
                List<GoodcangGrnList> existing = listMapper.selectByReceivingCodes(Collections.singletonList(code));
                GoodcangGrnList e = existing.isEmpty() ? new GoodcangGrnList() : existing.get(0);
                e.setReceivingCode(code);
                e.setWarehouseCode(str(item, "warehouse_code"));
                e.setReferenceNo(str(item, "reference_no"));
                e.setReceivingStatus(intVal(item, "receiving_status"));
                e.setCreateAt(parseDt(str(item, "create_at")));
                if (existing.isEmpty()) listMapper.insert(e); else listMapper.updateById(e);
                total++;
            }
            Object cnt = resp.get("count");
            if (cnt instanceof Number && ((Number) cnt).intValue() <= page * 200) break;
            if (data.size() < 200) break;
            page++;
        }
        return OperationSyncResult.success("gc_grn_list", "谷仓-入库单(全量)", "/inbound_order/get_grn_list", total, total, System.currentTimeMillis() - start);
    }

    /** 智能同步：表空拉90天，有数据拉30天 */
    public OperationSyncResult syncGrnListSmart() throws Exception
    {
        int days = listMapper.selectAll().isEmpty() ? 90 : 30;
        return syncGrnList(days);
    }

    /** 同步入库单列表(最近N天) */
    public OperationSyncResult syncGrnList(int daysBack) throws Exception
    {
        long start = System.currentTimeMillis();
        String from = LocalDateTime.now().minusDays(daysBack).format(DT);
        String to = LocalDateTime.now().format(DT);
        int total = 0, page = 1;
        while (true)
        {
            Map<String, Object> resp = client.getGrnList(from, to, page, 200);
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> data = (List<Map<String, Object>>) resp.get("data");
            if (data == null || data.isEmpty()) break;
            for (Map<String, Object> item : data)
            {
                String code = str(item, "receiving_code");
                if (code == null || code.isEmpty()) continue;
                List<GoodcangGrnList> existing = listMapper.selectByReceivingCodes(Collections.singletonList(code));
                GoodcangGrnList e = existing.isEmpty() ? new GoodcangGrnList() : existing.get(0);
                e.setReceivingCode(code);
                e.setWarehouseCode(str(item, "warehouse_code"));
                e.setReferenceNo(str(item, "reference_no"));
                e.setReceivingStatus(intVal(item, "receiving_status"));
                e.setCreateAt(parseDt(str(item, "create_at")));
                if (existing.isEmpty()) listMapper.insert(e); else listMapper.updateById(e);
                total++;
            }
            Object cnt = resp.get("count");
            if (cnt instanceof Number && ((Number) cnt).intValue() <= page * 200) break;
            if (data.size() < 200) break;
            page++;
        }
        return OperationSyncResult.success("gc_grn_list", "谷仓-入库单", "/inbound_order/get_grn_list", total, total, System.currentTimeMillis() - start);
    }

    /** 仅同步最近5天入库单详情（按create_at筛选） */
    public OperationSyncResult syncAllGrnDetails() throws Exception
    {
        long start = System.currentTimeMillis();
        List<GoodcangGrnList> recent = listMapper.selectRecentByCreateAt(5);
        LOG.info("谷仓入库单详情 最近5天: {}条", recent.size());

        int total = 0;
        for (GoodcangGrnList grn : recent)
        {
            try
            {
                Map<String, Object> resp = client.getGrnDetail(grn.getReceivingCode());
                @SuppressWarnings("unchecked")
                Map<String, Object> dd = (Map<String, Object>) resp.get("data");
                if (dd == null) continue;

                // 提取提货地址
                String ca1 = null;
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> collectingAddress = (List<Map<String, Object>>) dd.get("collecting_address");
                if (collectingAddress != null && !collectingAddress.isEmpty()) {
                    ca1 = str(collectingAddress.get(0), "ca_address1");
                }
                boolean caChanged = !Objects.equals(ca1, grn.getCaAddress1());
                if (caChanged) {
                    grn.setCaAddress1(ca1);
                    listMapper.updateCaAddress1(grn.getId(), ca1);
                }

                @SuppressWarnings("unchecked")
                List<Map<String, Object>> items = (List<Map<String, Object>>) dd.get("overseas_detail");
                if (items == null || items.isEmpty())
                    items = (List<Map<String, Object>>) dd.get("transfer_detail");
                if (items != null && !items.isEmpty())
                {
                    detailMapper.deleteByReceivingCode(grn.getReceivingCode());
                    List<GoodcangGrnDetail> batch = new ArrayList<>();
                    for (Map<String, Object> td : items)
                    {
                        GoodcangGrnDetail de = new GoodcangGrnDetail();
                        de.setReceivingCode(grn.getReceivingCode());
                        de.setProductSku(str(td, "product_sku"));
                        de.setBoxNo(str(td, "box_no"));
                        de.setTransitPreCount(intVal(td, "overseas_pre_count"));
                        de.setTransitReceivingCount(intVal(td, "overseas_receiving_count"));
                        batch.add(de);
                    }
                    detailMapper.batchInsert(batch);
                    total += batch.size();
                }
            }
            catch (Exception e) { LOG.warn("详情同步失败 {}: {}", grn.getReceivingCode(), e.getMessage()); }
        }
        return OperationSyncResult.success("gc_grn_detail", "谷仓-入库单详情(近5天)", "/inbound_order/get_grn_detail", total, total, System.currentTimeMillis() - start);
    }

    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? v.toString() : null; }
    private int intVal(Map<String, Object> m, String k) { Object v = m.get(k); if (v == null) return 0; try { return Integer.parseInt(v.toString()); } catch (Exception e) { return 0; } }
    private java.util.Date parseDt(String s) {
        if (s == null || s.isEmpty()) return null;
        try { return java.util.Date.from(LocalDateTime.parse(s, DT).atZone(java.time.ZoneId.systemDefault()).toInstant()); }
        catch (Exception e) { return null; }
    }
}
