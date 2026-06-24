package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.WarehouseStatement;
import com.ruoyi.system.mapper.operation.external.WarehouseStatementMapper;
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

/** 领星库存流水同步 → warehouse_statement，按 (wid,sku,opt_time) upsert */
@Service
public class LingxingStatementSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(LingxingStatementSyncService.class);
    private static final String API = "erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement";
    private static final DateTimeFormatter DT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");
    private static final SimpleDateFormat SDF = new SimpleDateFormat("yyyy-MM-dd HH:mm");

    private final LingxingGatewayService gw;
    private final WarehouseStatementMapper mapper;
    private final ObjectMapper om;

    public LingxingStatementSyncService(LingxingGatewayService gw, WarehouseStatementMapper mapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.om = om; }

    /** 日常增量：表空拉90天，有数据拉30天 */
    public OperationSyncResult sync() throws Exception {
        int days = mapper.selectAll().isEmpty() ? 90 : 30;
        return sync(LocalDate.now().minusDays(days), LocalDate.now(), 90);
    }

    /** 校准模式：按 windowDays 分段拉取，upsert 不清空 */
    public OperationSyncResult sync(LocalDate startDate, LocalDate endDate, int windowDays) throws Exception
    {
        long start = System.currentTimeMillis();
        Map<String, WarehouseStatement> existing = new HashMap<>();
        for (WarehouseStatement e : mapper.selectAll()) {
            String key = e.getWid() + "|" + e.getSku() + "|" + (e.getOptTime() != null ? SDF.format(e.getOptTime()) : "");
            existing.put(key, e);
        }

        int totalInserted = 0, totalUpdated = 0;
        LocalDate segStart = startDate;
        while (!segStart.isAfter(endDate)) {
            LocalDate segEnd = segStart.plusDays(windowDays);
            if (segEnd.isAfter(endDate)) segEnd = endDate;
            int[] r = syncSegment(segStart.toString(), segEnd.toString(), existing);
            totalInserted += r[0]; totalUpdated += r[1];
            segStart = segEnd.plusDays(1);
        }
        return OperationSyncResult.success("statement", "领星-库存流水", API, totalInserted+totalUpdated, totalInserted+totalUpdated, System.currentTimeMillis()-start);
    }

    private int[] syncSegment(String dateFrom, String dateTo, Map<String, WarehouseStatement> existing) throws Exception {
        int inserted = 0, updated = 0, offset = 0, length = 200;

        while (true)
        {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("wids", "18676,18701,18675,18674,18702,18700,18699");
            body.put("types", "22");
            body.put("start_date", dateFrom);
            body.put("end_date", dateTo);
            body.put("offset", offset);
            body.put("length", length);
            Map<String, Object> resp = gw.post(API, body);
            List<Map<String, Object>> list = getList(resp, "data");
            if (list.isEmpty()) break;
            int total = getInt(resp, "total");

            for (Map<String, Object> row : list)
            {
                Integer wid = intVal(row, "wid");
                String sku = str(row, "sku");
                Date optTime = parseDt(str(row, "opt_time"));
                String key = wid + "|" + sku + "|" + (optTime != null ? SDF.format(optTime) : "");
                WarehouseStatement e = existing.get(key);
                boolean isNew = (e == null);
                if (isNew) { e = new WarehouseStatement(); e.setWid(wid); e.setSku(sku); e.setOptTime(optTime); }

                e.setWareHouseName(str(row, "ware_house_name"));
                e.setType(intVal(row, "type"));

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
    private Date parseDt(String s) {
        if (!StringUtils.hasText(s)) return null;
        try { return java.util.Date.from(LocalDateTime.parse(s.length()==16?s:s.substring(0,16), DT).atZone(java.time.ZoneId.systemDefault()).toInstant()); }
        catch (Exception e) { return null; }
    }
}
