package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.OverseasStockOrder;
import com.ruoyi.system.mapper.operation.external.OverseasStockOrderMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.time.LocalDate;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 领星备货单号同步 → overseas_stock_order, 最近5天增量拉取 */
@Service
public class OverseasStockOrderSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(OverseasStockOrderSyncService.class);
    private static final String API = "erp/sc/routing/owms/inbound/listInbound";
    private static final int PAGE_SIZE = 50;
    private static final int RECENT_DAYS = 5;

    private final LingxingGatewayService gw;
    private final OverseasStockOrderMapper mapper;
    private final ObjectMapper om;

    public OverseasStockOrderSyncService(LingxingGatewayService gw, OverseasStockOrderMapper mapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.om = om; }

    public OperationSyncResult sync() throws Exception
    {
        long start = System.currentTimeMillis();
        Map<String, OverseasStockOrder> existing = new HashMap<>();
        for (OverseasStockOrder e : mapper.selectAll())
            existing.put(e.getOverseasOrderNo(), e);

        LocalDate endDate = LocalDate.now();
        LocalDate startDate = endDate.minusDays(RECENT_DAYS);
        int inserted = 0, updated = 0, processed = 0, page = 1, total = 0;
        while (true)
        {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("page", page);
            body.put("page_size", PAGE_SIZE);
            body.put("is_delete", 0);
            body.put("create_time_from", startDate.toString());
            body.put("create_time_to", endDate.toString());
            Map<String, Object> resp = gw.post(API, body);
            List<Map<String, Object>> data = getList(resp, "data");
            if (data.isEmpty()) break;

            for (Map<String, Object> item : data)
            {
                String orderNo = str(item, "overseas_order_no");
                if (orderNo == null || orderNo.isEmpty()) continue;
                processed++;
                OverseasStockOrder e = existing.get(orderNo);
                if (e == null)
                {
                    e = new OverseasStockOrder();
                    e.setOverseasOrderNo(orderNo);
                    e.setInboundOrderNo(str(item, "inbound_order_no"));
                    e.setCreateTime(new Date());
                    mapper.insert(e);
                    existing.put(orderNo, e);
                    inserted++;
                }
                else
                {
                    e.setOverseasOrderNo(orderNo);
                    e.setInboundOrderNo(str(item, "inbound_order_no"));
                    mapper.updateById(e);
                    updated++;
                }
            }
            Object t = resp.get("total");
            if (t instanceof Number) total = ((Number) t).intValue();
            if (total > 0 && page * PAGE_SIZE >= total) break;
            page++;
        }
        LOG.info("备货单号 最近{}天同步完成({}~{}), 拉取/处理 {} 条, 新增 {} 条, 覆盖 {} 条", RECENT_DAYS, startDate, endDate, processed, inserted, updated);
        // This is a five-day incremental window. No newly created order is a valid result,
        // not an API failure, and must not trigger retries or an enterprise-WeChat alert.
        OperationSyncResult result = OperationSyncResult.successAllowEmpty(
                "stock_order", "领星-备货单号", API,
                processed, processed, System.currentTimeMillis() - start);
        if (processed == 0)
        {
            result.setBusinessSummary("最近" + RECENT_DAYS + "天无新增备货单，本次增量同步正常完成");
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { if (r == null) return new ArrayList<>(); Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { List<Map<String, Object>> result = om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); return result != null ? result : new ArrayList<>(); } catch (Exception e) { return new ArrayList<>(); } }
    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? v.toString() : null; }
}
