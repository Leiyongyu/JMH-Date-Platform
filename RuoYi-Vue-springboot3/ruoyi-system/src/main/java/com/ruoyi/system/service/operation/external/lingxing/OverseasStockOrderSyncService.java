package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.OverseasStockOrder;
import com.ruoyi.system.mapper.operation.external.OverseasStockOrderMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 领星备货单号同步 → overseas_stock_order, 全量拉取 upsert */
@Service
public class OverseasStockOrderSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(OverseasStockOrderSyncService.class);
    private static final String API = "erp/sc/routing/owms/inbound/listInbound";

    private final LingxingGatewayService gw;
    private final OverseasStockOrderMapper mapper;
    private final ObjectMapper om;

    public OverseasStockOrderSyncService(LingxingGatewayService gw, OverseasStockOrderMapper mapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.om = om; }

    public OperationSyncResult sync() throws Exception
    {
        long start = System.currentTimeMillis();
        Set<String> existing = new HashSet<>();
        for (OverseasStockOrder e : mapper.selectAll())
            existing.add(e.getOverseasOrderNo());

        int inserted = 0, page = 1, total = 0;
        while (true)
        {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("page", page);
            body.put("page_size", 50);
            body.put("is_delete", 0);
            Map<String, Object> resp = gw.post(API, body);
            List<Map<String, Object>> data = getList(resp, "data");
            if (data.isEmpty()) break;

            for (Map<String, Object> item : data)
            {
                String orderNo = str(item, "overseas_order_no");
                if (orderNo == null || orderNo.isEmpty()) continue;
                if (!existing.contains(orderNo))
                {
                    OverseasStockOrder e = new OverseasStockOrder();
                    e.setOverseasOrderNo(orderNo);
                    e.setInboundOrderNo(str(item, "inbound_order_no"));
                    e.setCreateTime(new Date());
                    mapper.insert(e);
                    existing.add(orderNo);
                    inserted++;
                }
            }
            Object t = resp.get("total");
            if (t instanceof Number) total = ((Number) t).intValue();
            if (total > 0 && page * 50 >= total) break;
            page++;
        }
        LOG.info("备货单号 全量同步完成, 新增 {} 条", inserted);
        return OperationSyncResult.success("stock_order", "领星-备货单号", API, inserted, inserted, System.currentTimeMillis() - start);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return new ArrayList<>(); } }
    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? v.toString() : null; }
}
