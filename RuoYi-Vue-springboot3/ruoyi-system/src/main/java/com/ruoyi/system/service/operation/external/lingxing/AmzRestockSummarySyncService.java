package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzRestockSummary;
import com.ruoyi.system.mapper.operation.external.AmzRestockSummaryMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 领星 Amazon 补货建议 → amz_restock_summary。对齐旧项目：sid_list 分批、data_type=2、嵌套解析 basic_info/amazon_quantity_info/sales_info/item_list */
@Service
public class AmzRestockSummarySyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzRestockSummarySyncService.class);
    private static final String API = "erp/sc/routing/restocking/analysis/getSummaryList";
    private static final int PAGE_SIZE = 50;
    private static final int SID_BATCH_SIZE = 20;

    private final LingxingGatewayService gw;
    private final AmzRestockSummaryMapper mapper;
    private final ShopListMapper shopMapper;
    private final ObjectMapper om;

    public AmzRestockSummarySyncService(LingxingGatewayService gw, AmzRestockSummaryMapper mapper, ShopListMapper shopMapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.shopMapper = shopMapper; this.om = om; }

    public OperationSyncResult syncAll() throws Exception
    {
        long start = System.currentTimeMillis();
        List<String> sids = shopMapper.selectSidsByPlatform("10001", 1);
        if (sids.isEmpty())
            return OperationSyncResult.success("amz_restock", "领星-Amazon补货建议", API, 0, 0, System.currentTimeMillis()-start);

        mapper.deleteAll();
        Set<String> seen = new HashSet<>();
        int total = 0;

        for (int i = 0; i < sids.size(); i += SID_BATCH_SIZE)
        {
            List<String> batch = sids.subList(i, Math.min(i + SID_BATCH_SIZE, sids.size()));
            int offset = 0;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("data_type", 2);
                body.put("offset", offset); body.put("length", PAGE_SIZE);
                body.put("sid_list", batch);
                Map<String, Object> resp = gw.post(API, body);
                List<Map<String, Object>> data = getList(resp, "data");
                if (data.isEmpty()) break;

                List<AmzRestockSummary> list = new ArrayList<>();
                for (Map<String, Object> item : data)
                {
                    collectItems(list, item);
                    // 遍历子项 item_list
                    List<Map<String, Object>> children = getList(item, "item_list");
                    if (children != null)
                        for (Map<String, Object> child : children) collectItems(list, child);
                }
                // 去重
                List<AmzRestockSummary> fresh = new ArrayList<>();
                for (AmzRestockSummary e : list)
                    if (seen.add(e.getHashId())) fresh.add(e);
                if (!fresh.isEmpty()) { mapper.batchInsert(fresh); total += fresh.size(); }
                if (data.size() < PAGE_SIZE) break;
                offset += PAGE_SIZE;
            }
            if (i + SID_BATCH_SIZE < sids.size()) Thread.sleep(2000);
        }
        return OperationSyncResult.success("amz_restock", "领星-Amazon补货建议", API, total, total, System.currentTimeMillis()-start);
    }

    private void collectItems(List<AmzRestockSummary> result, Map<String, Object> item)
    {
        Map<String, Object> basic = getMap(item, "basic_info");
        if (basic == null) return;
        String hashId = str(basic, "hash_id");
        if (hashId.isEmpty()) return;
        Integer sid = intObj(basic, "sid");
        String msku = firstMsku(basic);
        if (sid == null || msku == null || msku.isEmpty()) return;

        Map<String, Object> qty = getMap(item, "amazon_quantity_info");
        Map<String, Object> sales = getMap(item, "sales_info");

        AmzRestockSummary e = new AmzRestockSummary();
        e.setHashId(hashId);
        e.setSid(sid);
        e.setMsku(msku);
        e.setFbaSellable(qty != null ? intVal(qty, "amazon_quantity_valid") : 0);
        e.setFbaInbound(qty != null ? intVal(qty, "amazon_quantity_shipping") : 0);
        e.setFbaReserved(qty != null ? intVal(qty, "afn_reserved_quantity") : 0);
        e.setSales7d(sales != null ? intVal(sales, "sales_total_7") : 0);
        e.setSales14d(sales != null ? intVal(sales, "sales_total_14") : 0);
        e.setSales30d(sales != null ? intVal(sales, "sales_total_30") : 0);
        e.setSales60d(sales != null ? intVal(sales, "sales_total_60") : 0);
        e.setAvgSales14d(sales != null ? bd(sales, "sales_avg_14") : null);
        e.setAvgSales30d(sales != null ? bd(sales, "sales_avg_30") : null);
        e.setAvgSales60d(sales != null ? bd(sales, "sales_avg_60") : null);
        result.add(e);
    }

    @SuppressWarnings("unchecked")
    private String firstMsku(Map<String, Object> basic)
    {
        Object listObj = basic.get("msku_fnsku_list");
        if (listObj instanceof List) {
            List<Map<String, Object>> list = (List<Map<String, Object>>) listObj;
            if (!list.isEmpty()) { Object msku = list.get(0).get("msku"); return msku != null ? String.valueOf(msku) : ""; }
        }
        return "";
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return new ArrayList<>(); } }
    @SuppressWarnings("unchecked")
    private Map<String, Object> getMap(Map<String, Object> m, String k) { Object v = m.get(k); return v instanceof Map ? (Map<String, Object>) v : null; }
    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? String.valueOf(v) : ""; }
    private int intVal(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number)v).intValue(); if (v != null) try { return Integer.parseInt(v.toString()); } catch (Exception e) {} return 0; }
    private Integer intObj(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number)v).intValue(); if (v != null) try { return Integer.parseInt(v.toString()); } catch (Exception e) {} return null; }
    private BigDecimal bd(Map<String, Object> m, String k) { Object v = m.get(k); if (v == null) return null; if (v instanceof Number) return BigDecimal.valueOf(((Number)v).doubleValue()); try { return new BigDecimal(v.toString()); } catch (Exception e) { return null; } }
}
