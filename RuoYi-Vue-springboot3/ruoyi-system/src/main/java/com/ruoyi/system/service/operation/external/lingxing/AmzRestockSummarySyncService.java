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

/** 领星 Amazon 补货建议同步 → amz_restock_summary */
@Service
public class AmzRestockSummarySyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzRestockSummarySyncService.class);
    private static final String API = "erp/sc/routing/restocking/analysis/getSummaryList";
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
        if (sids.isEmpty()) return OperationSyncResult.success("amz_restock", "领星-Amazon补货建议", API, 0, 0, System.currentTimeMillis() - start);
        mapper.deleteAll();
        int total = 0;
        for (String sid : sids)
        {
            int offset = 0, length = 200;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("sid", sid); body.put("offset", offset); body.put("length", length);
                Map<String, Object> resp = gw.post(API, body);
                List<Map<String, Object>> list = getList(resp, "data");
                if (list.isEmpty()) break;
                List<AmzRestockSummary> batch = new ArrayList<>();
                for (Map<String, Object> row : list)
                {
                    AmzRestockSummary e = new AmzRestockSummary();
                    e.setHashId(str(row, "hash_id", "hashId"));
                    e.setSid(Integer.parseInt(sid));
                    e.setMsku(str(row, "msku"));
                    e.setFbaSellable(intVal(row, "fba_sellable", "fbaSellable"));
                    e.setFbaInbound(intVal(row, "fba_inbound", "fbaInbound"));
                    e.setSales7d(intVal(row, "sales_7d", "sales7d"));
                    e.setSales14d(intVal(row, "sales_14d", "sales14d"));
                    e.setSales30d(intVal(row, "sales_30d", "sales30d"));
                    e.setSales60d(intVal(row, "sales_60d", "sales60d"));
                    e.setAvgSales14d(bd(row, "avg_sales_14d", "avgSales14d"));
                    e.setAvgSales30d(bd(row, "avg_sales_30d", "avgSales30d"));
                    e.setAvgSales60d(bd(row, "avg_sales_60d", "avgSales60d"));
                    batch.add(e);
                }
                mapper.batchInsert(batch); total += batch.size();
                if (list.size() < length) break;
                offset += length;
            }
        }
        return OperationSyncResult.success("amz_restock", "领星-Amazon补货建议", API, total, total, System.currentTimeMillis() - start);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return new ArrayList<>(); } }
    private String str(Map<String, Object> m, String... ks) { for (String k : ks) { Object v = m.get(k); if (v != null && StringUtils.hasText(v.toString())) return v.toString(); } return null; }
    private Integer intVal(Map<String, Object> m, String... ks) { String s = str(m, ks); return s != null ? Integer.valueOf(s) : null; }
    private BigDecimal bd(Map<String, Object> m, String... ks) { String s = str(m, ks); return s != null ? new BigDecimal(s) : null; }
}
