package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzOrderProfit;
import com.ruoyi.system.mapper.operation.external.AmzOrderProfitMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 领星 Amazon 订单利润同步 → amz_order_profit。对齐旧项目：sids 分批、startDate/endDate、price_list[0] 取 sid/seller_sku */
@Service
public class AmzOrderProfitSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzOrderProfitSyncService.class);
    private static final String API = "basicOpen/finance/mreport/OrderProfit";
    private static final int PAGE_SIZE = 5000;
    private static final int SID_BATCH_SIZE = 20;

    private final LingxingGatewayService gw;
    private final AmzOrderProfitMapper mapper;
    private final ShopListMapper shopMapper;
    private final ObjectMapper om;

    public AmzOrderProfitSyncService(LingxingGatewayService gw, AmzOrderProfitMapper mapper, ShopListMapper shopMapper, ObjectMapper om)
    { this.gw = gw; this.mapper = mapper; this.shopMapper = shopMapper; this.om = om; }

    public OperationSyncResult syncAll() throws Exception
    {
        long start = System.currentTimeMillis();
        List<String> sids = shopMapper.selectSidsByPlatform("10001", 1);
        if (sids.isEmpty())
            return OperationSyncResult.success("amz_profit", "领星-Amazon订单利润", API, 0, 0, System.currentTimeMillis()-start);

        LocalDate end = LocalDate.now().minusDays(1);
        LocalDate startDate = end.minusDays(30);
        mapper.deleteAll();

        int total = 0;
        for (int i = 0; i < sids.size(); i += SID_BATCH_SIZE)
        {
            List<String> batch = sids.subList(i, Math.min(i + SID_BATCH_SIZE, sids.size()));
            int offset = 0;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("offset", offset); body.put("length", PAGE_SIZE);
                body.put("startDate", startDate.toString()); body.put("endDate", end.toString());
                body.put("sids", batch.stream().map(Integer::parseInt).collect(java.util.stream.Collectors.toList()));
                Map<String, Object> resp = gw.post(API, body);
                List<Map<String, Object>> data = getList(resp, "data");
                if (data.isEmpty()) break;

                List<AmzOrderProfit> list = new ArrayList<>();
                for (Map<String, Object> item : data)
                {
                    List<Map<String, Object>> priceList = getList(item, "price_list");
                    if (priceList == null || priceList.isEmpty()) continue;
                    Map<String, Object> pl = priceList.get(0);
                    AmzOrderProfit e = new AmzOrderProfit();
                    e.setSid(intVal(pl, "sid"));
                    e.setSellerSku(str(pl, "seller_sku"));
                    e.setGrossMargin(bd(item, "gross_margin"));
                    e.setSpendRate(bd(item, "spend_rate"));
                    e.setRefundAmountRate(bd(item, "refund_amount_rate"));
                    list.add(e);
                }
                if (!list.isEmpty()) { mapper.batchInsert(list); total += list.size(); }
                int remoteTotal = getInt(resp, "total");
                if (remoteTotal > 0 && offset + PAGE_SIZE >= remoteTotal) break;
                if (data.size() < PAGE_SIZE) break;
                offset += PAGE_SIZE;
            }
            if (i + SID_BATCH_SIZE < sids.size()) Thread.sleep(2000);
        }
        return OperationSyncResult.success("amz_profit", "领星-Amazon订单利润", API, total, total, System.currentTimeMillis()-start);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return new ArrayList<>(); } }
    private String str(Map<String, Object> m, String k) { Object v = m.get(k); return v != null ? String.valueOf(v) : ""; }
    private Integer intVal(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number)v).intValue(); if (v != null) try { return Integer.parseInt(v.toString()); } catch (Exception e) {} return 0; }
    private int getInt(Map<String, Object> m, String k) { Object v = m.get(k); if (v instanceof Number) return ((Number)v).intValue(); return 0; }
    private BigDecimal bd(Map<String, Object> m, String k) { Object v = m.get(k); if (v == null) return BigDecimal.ZERO; if (v instanceof Number) return BigDecimal.valueOf(((Number)v).doubleValue()); try { return new BigDecimal(v.toString()); } catch (Exception e) { return BigDecimal.ZERO; } }
}
