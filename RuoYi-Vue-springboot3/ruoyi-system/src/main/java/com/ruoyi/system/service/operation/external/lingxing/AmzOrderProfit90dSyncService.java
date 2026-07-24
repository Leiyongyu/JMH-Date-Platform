package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzOrderProfit;
import com.ruoyi.system.mapper.operation.external.AmzOrderProfit90dMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;

/** 每日同步 Amazon 最近90个自然日的 MSKU 毛利率。 */
@Service
public class AmzOrderProfit90dSyncService
{
    private static final String API = "basicOpen/finance/mreport/OrderProfit";
    private static final int PAGE_SIZE = 5000;
    private static final int SID_BATCH_SIZE = 20;

    private final LingxingGatewayService gateway;
    private final AmzOrderProfit90dMapper mapper;
    private final ShopListMapper shopMapper;
    private final ObjectMapper objectMapper;

    public AmzOrderProfit90dSyncService(LingxingGatewayService gateway,
                                        AmzOrderProfit90dMapper mapper,
                                        ShopListMapper shopMapper,
                                        ObjectMapper objectMapper)
    {
        this.gateway = gateway;
        this.mapper = mapper;
        this.shopMapper = shopMapper;
        this.objectMapper = objectMapper;
    }

    public OperationSyncResult syncAll() throws Exception
    {
        long startedMillis = System.currentTimeMillis();
        // sync_time 使用秒精度，阈值向前留一秒，避免本轮首批同秒写入的数据被误清理。
        Date syncStartedAt = new Date(startedMillis - 1000);
        List<String> sids = shopMapper.selectSidsByPlatform("10001", 1);
        if (sids.isEmpty())
        {
            return OperationSyncResult.success("amz_profit_90d", "领星-Amazon最近90天利润率",
                    API, 0, 0, System.currentTimeMillis() - startedMillis);
        }

        LocalDate endDate = LocalDate.now();
        LocalDate startDate = endDate.minusDays(89);
        int total = 0;
        for (int i = 0; i < sids.size(); i += SID_BATCH_SIZE)
        {
            List<String> sidBatch = sids.subList(i, Math.min(i + SID_BATCH_SIZE, sids.size()));
            int offset = 0;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("offset", offset);
                body.put("length", PAGE_SIZE);
                body.put("startDate", startDate.toString());
                body.put("endDate", endDate.toString());
                body.put("sids", sidBatch.stream().map(Integer::parseInt).collect(Collectors.toList()));

                Map<String, Object> response = gateway.post(API, body);
                List<Map<String, Object>> data = getList(response, "data");
                if (data.isEmpty()) break;

                List<AmzOrderProfit> rows = new ArrayList<>();
                for (Map<String, Object> item : data)
                {
                    List<Map<String, Object>> priceList = getList(item, "price_list");
                    if (priceList.isEmpty()) continue;
                    Map<String, Object> price = priceList.get(0);
                    String sellerSku = stringValue(price, "seller_sku");
                    if (sellerSku.isEmpty()) continue;

                    AmzOrderProfit row = new AmzOrderProfit();
                    row.setSid(integerValue(price, "sid"));
                    row.setSellerSku(sellerSku);
                    row.setGrossMargin(decimalValue(item, "gross_margin"));
                    rows.add(row);
                }
                if (!rows.isEmpty())
                {
                    mapper.batchUpsert(rows);
                    total += rows.size();
                }

                int remoteTotal = integerValue(response, "total");
                if ((remoteTotal > 0 && offset + PAGE_SIZE >= remoteTotal) || data.size() < PAGE_SIZE) break;
                offset += PAGE_SIZE;
            }
            if (i + SID_BATCH_SIZE < sids.size()) Thread.sleep(2000);
        }

        mapper.deleteNotSyncedSince(syncStartedAt);
        return OperationSyncResult.success("amz_profit_90d", "领星-Amazon最近90天利润率",
                API, total, total, System.currentTimeMillis() - startedMillis);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> source, String key)
    {
        if (source == null) return new ArrayList<>();
        Object value = source.get(key);
        if (value instanceof List) return (List<Map<String, Object>>) value;
        try
        {
            List<Map<String, Object>> result = objectMapper.convertValue(
                    value, new TypeReference<List<Map<String, Object>>>() {});
            return result != null ? result : new ArrayList<>();
        }
        catch (Exception ignored)
        {
            return new ArrayList<>();
        }
    }

    private String stringValue(Map<String, Object> source, String key)
    {
        Object value = source.get(key);
        return value == null ? "" : String.valueOf(value).trim();
    }

    private Integer integerValue(Map<String, Object> source, String key)
    {
        Object value = source == null ? null : source.get(key);
        if (value instanceof Number) return ((Number) value).intValue();
        if (value != null)
        {
            try { return Integer.parseInt(value.toString()); }
            catch (NumberFormatException ignored) { }
        }
        return 0;
    }

    private BigDecimal decimalValue(Map<String, Object> source, String key)
    {
        Object value = source.get(key);
        if (value == null) return null;
        if (value instanceof BigDecimal) return (BigDecimal) value;
        try { return new BigDecimal(value.toString()); }
        catch (NumberFormatException ignored) { return null; }
    }
}
