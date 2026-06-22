package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.PurchaseOrder;
import com.ruoyi.system.mapper.operation.external.PurchaseOrderMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.text.SimpleDateFormat;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 领星采购单同步 → purchase_order，按 (order_sn, create_time) upsert */
@Service
public class LingxingPurchaseOrderSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(LingxingPurchaseOrderSyncService.class);
    private static final String API = "erp/sc/routing/data/local_inventory/purchaseOrderList";
    private static final DateTimeFormatter DT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final SimpleDateFormat SDF = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");

    private final LingxingGatewayService gw;
    private final PurchaseOrderMapper mapper;
    private final ObjectMapper om;

    public LingxingPurchaseOrderSyncService(LingxingGatewayService gw, PurchaseOrderMapper mapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.om = om; }

    /** 日常增量：拉前一天 */
    public OperationSyncResult sync() throws Exception {
        boolean empty = mapper.selectAll().isEmpty();
        LocalDate today = LocalDate.now();
        if (empty)
        {
            LOG.info("purchase_order is empty, initialize Lingxing purchase orders for last 90 days");
            return sync(today.minusDays(90), today, 90);
        }
        return sync(today.minusDays(1), today.minusDays(1), 90);
    }

    /** 校准模式：按 windowDays 分段拉取，upsert 不清空 */
    public OperationSyncResult sync(LocalDate startDate, LocalDate endDate, int windowDays) throws Exception
    {
        long start = System.currentTimeMillis();
        Map<String, PurchaseOrder> existing = new HashMap<>();
        for (PurchaseOrder e : mapper.selectAll())
            existing.put(e.getOrderSn() + "|" + (e.getCreateTime() != null ? SDF.format(e.getCreateTime()) : ""), e);

        int totalInserted = 0, totalUpdated = 0;
        LocalDate seg = startDate;
        while (!seg.isAfter(endDate)) {
            LocalDate segEnd = seg.plusDays(windowDays);
            if (segEnd.isAfter(endDate)) segEnd = endDate;
            int[] r = syncSegment(seg.toString(), segEnd.toString(), existing);
            totalInserted += r[0]; totalUpdated += r[1];
            seg = segEnd.plusDays(1);
        }
        return OperationSyncResult.success("purchase_order", "领星-采购单", API, totalInserted+totalUpdated, totalInserted+totalUpdated, System.currentTimeMillis()-start);
    }

    private int[] syncSegment(String dateFrom, String dateTo, Map<String, PurchaseOrder> existing) throws Exception {
        int inserted = 0, updated = 0, offset = 0, length = 500;

        while (true)
        {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("search_field_time", "create_time");
            body.put("start_date", dateFrom); body.put("end_date", dateTo);
            body.put("offset", offset); body.put("length", length);
            Map<String, Object> resp = gw.post(API, body);
            List<Map<String, Object>> list = getList(resp, "data");
            if (list.isEmpty()) break;
            int total = getInt(resp, "total");

            for (Map<String, Object> row : list)
            {
                String orderSn = str(row, "order_sn");
                if (orderSn == null || orderSn.isEmpty()) continue;
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> items = (List<Map<String, Object>>) row.get("item_list");
                if (items == null || items.isEmpty()) continue;

                Date createTime = parseDt(str(row, "create_time"));
                String key = orderSn + "|" + (createTime != null ? SDF.format(createTime) : "");
                PurchaseOrder e = existing.get(key);
                boolean isNew = (e == null);
                if (isNew) e = new PurchaseOrder();

                e.setOrderSn(orderSn);
                e.setCustomOrderSn(str(row, "custom_order_sn"));
                e.setSupplierId(intVal(row, "supplier_id"));
                e.setSupplierName(str(row, "supplier_name"));
                e.setOptUid(intVal(row, "opt_uid"));
                e.setOptRealname(str(row, "opt_realname"));
                e.setAuditorRealname(str(row, "auditor_realname"));
                e.setLastRealname(str(row, "last_realname"));
                e.setOrderTime(parseDt(str(row, "order_time")));
                e.setUpdateTime(parseDt(str(row, "update_time")));
                e.setStatus(intVal(row, "status"));
                e.setStatusText(str(row, "status_text"));
                e.setWid(intVal(row, "wid"));
                e.setWareHouseName(str(row, "ware_house_name"));
                e.setCreateTime(createTime);

                Map<String, Object> firstItem = items.get(0);
                e.setItemSku(str(firstItem, "sku"));
                e.setItemProductName(str(firstItem, "product_name"));
                e.setItemProductId(intVal(firstItem, "product_id"));
                e.setItemQuantityReal(intVal(firstItem, "quantity_real"));
                e.setItemQuantityEntry(intVal(firstItem, "quantity_entry"));
                e.setItemQuantityReceive(intVal(firstItem, "quantity_receive"));
                e.setItemPrice(bdVal(firstItem, "price"));
                e.setItemAmount(bdVal(firstItem, "amount"));

                if (isNew) { mapper.insert(e); existing.put(key, e); inserted++; }
                else { mapper.updateById(e); updated++; }
            }
            offset += length;
            if (total <= 0 || offset >= total) break;
        }
        return new int[]{inserted, updated};
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return new ArrayList<>(); } }
    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? v.toString() : null; }
    private int getInt(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number)v).intValue(); return 0; }
    private Integer intVal(Map<String, Object> m, String k) { String s = str(m, k); return s != null ? Integer.valueOf(s) : null; }
    private BigDecimal bdVal(Map<String, Object> m, String k) { String s = str(m, k); return s != null ? new BigDecimal(s) : null; }
    private Date parseDt(String s) {
        if (!StringUtils.hasText(s)) return null;
        try { return java.util.Date.from(LocalDateTime.parse(s, DT).atZone(java.time.ZoneId.systemDefault()).toInstant()); }
        catch (Exception e) { return null; }
    }
}
