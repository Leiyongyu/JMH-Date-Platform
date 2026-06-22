package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzFbaShipment;
import com.ruoyi.system.mapper.operation.external.AmzFbaShipmentMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.text.SimpleDateFormat;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * 领星 Amazon FBA 货件同步 → amz_fba_shipment。
 * API: /erp/sc/data/fba_report/shipmentList
 * 每行 item 展平为一个明细记录，按 (sid, shipment_id, sku) 唯一键 upsert。
 */
@Service
public class AmzFbaShipmentSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzFbaShipmentSyncService.class);
    private static final String API = "erp/sc/data/fba_report/shipmentList";
    // API 返回 gmt_create/gmt_modified 格式为 yyyy-MM-dd HH:mm（无秒）
    private static final DateTimeFormatter[] DT_FORMATS = {
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"),
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")
    };

    private final LingxingGatewayService gw;
    private final AmzFbaShipmentMapper mapper;
    private final ShopListMapper shopMapper;
    private final ObjectMapper om;

    public AmzFbaShipmentSyncService(LingxingGatewayService gw, AmzFbaShipmentMapper mapper,
                                      ShopListMapper shopMapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.om = om; this.shopMapper = shopMapper; }

    /** 日常增量：拉最近5天；表为空则拉最近365天 */
    public OperationSyncResult sync() throws Exception
    {
        LocalDate end = LocalDate.now();
        int days = mapper.count() == 0 ? 365 : 5;
        LocalDate start = end.minusDays(days);
        return sync(start, end);
    }

    /** 校准模式：指定日期范围全量拉取并 upsert */
    public OperationSyncResult sync(LocalDate startDate, LocalDate endDate) throws Exception
    {
        long start = System.currentTimeMillis();
        List<String> sids = shopMapper.selectSidsByPlatform("10001", 1);
        if (sids.isEmpty())
        {
            return OperationSyncResult.success("amz_fba_shipment", "领星-FBA货件", API, 0, 0, System.currentTimeMillis() - start);
        }

        int total = 0, pageSize = 200;
        // 每批20个sid
        for (int i = 0; i < sids.size(); i += 20)
        {
            List<String> batch = sids.subList(i, Math.min(i + 20, sids.size()));
            int offset = 0;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("sid", String.join(",", batch));
                body.put("start_date", startDate.toString());
                body.put("end_date", endDate.toString());
                body.put("offset", offset);
                body.put("length", pageSize);
                Map<String, Object> resp = gw.post(API, body);
                List<Map<String, Object>> data = getDataList(resp);
                if (data.isEmpty()) break;

                List<AmzFbaShipment> rows = new ArrayList<>();
                for (Map<String, Object> shipment : data)
                {
                    Integer sid = intVal(shipment, "sid");
                    String username = str(shipment, "username");
                    String shipmentId = str(shipment, "shipment_id");
                    String shipmentName = str(shipment, "shipment_name");
                    Date gmtCreate = parseDt(str(shipment, "gmt_create"));
                    Date gmtModified = parseDt(str(shipment, "gmt_modified"));
                    if (sid == null) continue;

                    @SuppressWarnings("unchecked")
                    List<Map<String, Object>> items = (List<Map<String, Object>>) shipment.get("item_list");
                    if (items == null || items.isEmpty()) continue;

                    for (Map<String, Object> item : items)
                    {
                        String msku = str(item, "msku");
                        String sku = str(item, "sku");
                        if (sku == null || sku.isEmpty()) sku = msku;
                        if (sku == null || sku.isEmpty()) continue;

                        AmzFbaShipment row = new AmzFbaShipment();
                        row.setSid(sid);
                        row.setUsername(username);
                        row.setShipmentId(shipmentId != null ? shipmentId : "");
                        row.setShipmentName(shipmentName != null ? shipmentName : "");
                        row.setMsku(msku != null ? msku : "");
                        row.setSku(sku);
                        row.setQuantityShipped(intVal(item, "quantity_shipped"));
                        row.setInitQuantityShipped(intVal(item, "init_quantity_shipped"));
                        row.setQuantityReceived(intVal(item, "quantity_received"));
                        row.setQuantityShippedLocal(intVal(item, "quantity_shipped_local"));
                        row.setGmtCreate(gmtCreate);
                        row.setGmtModified(gmtModified);
                        rows.add(row);
                    }
                }
                if (!rows.isEmpty()) { mapper.batchUpsert(rows); total += rows.size(); }

                int remoteTotal = getInt(resp, "total");
                if (remoteTotal > 0 && offset + pageSize >= remoteTotal) break;
                if (data.size() < pageSize) break;
                offset += pageSize;
            }
            if (i + 20 < sids.size()) Thread.sleep(1000);
        }
        return OperationSyncResult.success("amz_fba_shipment", "领星-FBA货件", API, total, total, System.currentTimeMillis() - start);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getDataList(Map<String, Object> resp)
    {
        Object d = resp.get("data");
        if (d instanceof Map) {
            Object list = ((Map<String, Object>) d).get("list");
            if (list instanceof List) return (List<Map<String, Object>>) list;
            try { return om.convertValue(list, new TypeReference<List<Map<String, Object>>>() {}); }
            catch (Exception e) { return new ArrayList<>(); }
        }
        return new ArrayList<>();
    }

    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? String.valueOf(v) : null; }
    private int getInt(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number) v).intValue(); return 0; }
    private Integer intVal(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number) v).intValue(); if (v != null) try { return Integer.parseInt(v.toString()); } catch (Exception e) {} return 0; }
    private Date parseDt(String s) {
        if (!StringUtils.hasText(s)) return null;
        for (DateTimeFormatter fmt : DT_FORMATS) {
            try { return java.util.Date.from(LocalDateTime.parse(s, fmt).atZone(java.time.ZoneId.systemDefault()).toInstant()); }
            catch (Exception ignored) {}
        }
        return null;
    }
}
