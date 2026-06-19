package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzOrderProfit;
import com.ruoyi.system.mapper.operation.external.AmzOrderProfitMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 领星 Amazon 订单利润同步 → amz_order_profit */
@Service
public class AmzOrderProfitSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzOrderProfitSyncService.class);
    private static final String API = "basicOpen/finance/mreport/OrderProfit";
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
        if (sids.isEmpty()) return OperationSyncResult.success("amz_profit", "领星-Amazon订单利润", API, 0, 0, System.currentTimeMillis() - start);
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
                List<AmzOrderProfit> batch = new ArrayList<>();
                for (Map<String, Object> row : list)
                {
                    AmzOrderProfit e = new AmzOrderProfit();
                    e.setSid(Integer.parseInt(sid));
                    e.setSellerSku(str(row, "seller_sku", "sellerSku"));
                    e.setGrossMargin(bd(row, "gross_margin", "grossMargin"));
                    e.setSpendRate(bd(row, "spend_rate", "spendRate"));
                    e.setRefundAmountRate(bd(row, "refund_amount_rate", "refundAmountRate"));
                    batch.add(e);
                }
                mapper.batchInsert(batch); total += batch.size();
                if (list.size() < length) break;
                offset += length;
            }
        }
        return OperationSyncResult.success("amz_profit", "领星-Amazon订单利润", API, total, total, System.currentTimeMillis() - start);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> r, String k)
    { Object o = r.get(k); if (o instanceof List) return (List<Map<String, Object>>) o; try { return om.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); } catch (Exception e) { return new ArrayList<>(); } }
    private String str(Map<String, Object> m, String... ks) { for (String k : ks) { Object v = m.get(k); if (v != null && StringUtils.hasText(v.toString())) return v.toString(); } return null; }
    private BigDecimal bd(Map<String, Object> m, String... ks) { String s = str(m, ks); return s != null ? new BigDecimal(s) : null; }
}
