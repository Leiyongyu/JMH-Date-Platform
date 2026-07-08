package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.AmzProductPerformanceInventory;
import com.ruoyi.system.mapper.operation.external.AmzProductPerformanceInventoryMapper;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 领星产品表现 → AMZ FBA 库存口径。 */
@Service
public class AmzProductPerformanceInventorySyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzProductPerformanceInventorySyncService.class);
    private static final String API = "bd/productPerformance/openApi/asinList";
    private static final int PAGE_SIZE = 5000;
    private static final int SID_BATCH_SIZE = 200;
    private static final int LOOKBACK_DAYS = 90;

    private final LingxingGatewayService gw;
    private final AmzProductPerformanceInventoryMapper mapper;
    private final ShopListMapper shopMapper;
    private final ObjectMapper om;

    public AmzProductPerformanceInventorySyncService(LingxingGatewayService gw,
                                                     AmzProductPerformanceInventoryMapper mapper,
                                                     ShopListMapper shopMapper,
                                                     ObjectMapper om)
    {
        this.gw = gw;
        this.mapper = mapper;
        this.shopMapper = shopMapper;
        this.om = om;
    }

    public OperationSyncResult syncAll() throws Exception
    {
        long start = System.currentTimeMillis();
        List<String> sidStrings = shopMapper.selectSidsByPlatform("10001", 1);
        if (sidStrings.isEmpty())
            return OperationSyncResult.success("amz_product_inventory", "领星-Amazon产品表现库存", API, 0, 0, System.currentTimeMillis() - start);

        mapper.deleteAll();
        Set<String> seen = new HashSet<>();
        int total = 0;
        LocalDate endDate = LocalDate.now();
        LocalDate startDate = endDate.minusDays(LOOKBACK_DAYS - 1L);

        for (int i = 0; i < sidStrings.size(); i += SID_BATCH_SIZE)
        {
            List<Integer> sidBatch = toIntList(sidStrings.subList(i, Math.min(i + SID_BATCH_SIZE, sidStrings.size())));
            int offset = 0;
            while (true)
            {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("offset", offset);
                body.put("length", PAGE_SIZE);
                body.put("sort_field", "volume");
                body.put("sort_type", "desc");
                body.put("sid", sidBatch);
                body.put("start_date", startDate.toString());
                body.put("end_date", endDate.toString());
                body.put("summary_field", "msku");
                body.put("currency_code", "CNY");
                body.put("is_recently_enum", false);
                body.put("purchase_status", 0);

                Map<String, Object> resp = gw.post(API, body);
                Map<String, Object> data = getMap(resp, "data");
                List<Map<String, Object>> rows = getList(data, "list");
                if (rows.isEmpty()) break;

                List<AmzProductPerformanceInventory> batch = new ArrayList<>();
                for (Map<String, Object> row : rows)
                {
                    AmzProductPerformanceInventory entity = toEntity(row);
                    if (entity == null) continue;
                    String key = entity.getSid() + "|" + entity.getSellerSku();
                    if (seen.add(key)) batch.add(entity);
                }
                if (!batch.isEmpty())
                {
                    mapper.batchInsert(batch);
                    total += batch.size();
                }

                int remoteTotal = getInt(data, "total");
                if (remoteTotal > 0 && offset + PAGE_SIZE >= remoteTotal) break;
                if (rows.size() < PAGE_SIZE) break;
                offset += PAGE_SIZE;
                Thread.sleep(10000);
            }
            if (i + SID_BATCH_SIZE < sidStrings.size()) Thread.sleep(10000);
        }

        LOG.info("领星-Amazon产品表现库存同步完成: {} 条", total);
        return OperationSyncResult.success("amz_product_inventory", "领星-Amazon产品表现库存", API, total, total, System.currentTimeMillis() - start);
    }

    private AmzProductPerformanceInventory toEntity(Map<String, Object> row)
    {
        Map<String, Object> price = firstMap(row, "price_list");
        Integer sid = price != null ? intObj(price, "sid") : firstInt(row, "sids");
        String sellerSku = price != null ? str(price, "seller_sku") : "";
        String localSku = price != null ? str(price, "local_sku") : str(row, "sku");
        if (sid == null || sellerSku.isEmpty()) return null;

        Map<String, Object> available = getMap(row, "available_inventory");
        int fulfillable = intVal(available, row, "afn_fulfillable_quantity");
        int transfer = intVal(available, row, "reserved_fc_transfers");
        int receiving = intVal(available, row, "afn_inbound_receiving_quantity");
        int customerOrders = intVal(available, row, "reserved_customerorders");
        int processing = intVal(available, row, "reserved_fc_processing");
        int reserved = customerOrders + processing;
        int inbound = intVal(available, row, "afn_inbound_shipped_quantity");
        int inboundWorking = intVal(available, row, "afn_inbound_working_quantity");

        AmzProductPerformanceInventory entity = new AmzProductPerformanceInventory();
        entity.setSid(sid);
        entity.setSellerSku(sellerSku);
        entity.setLocalSku(localSku);
        entity.setFbaFulfillable(fulfillable);
        entity.setFbaTransfer(transfer);
        entity.setFbaReceiving(receiving);
        entity.setFbaReserved(reserved);
        entity.setFbaInbound(inbound);
        entity.setFbaInboundWorking(inboundWorking);
        entity.setFbaStock(fulfillable + transfer + receiving + reserved);
        return entity;
    }

    private List<Integer> toIntList(List<String> values)
    {
        List<Integer> result = new ArrayList<>();
        for (String value : values)
        {
            try { result.add(Integer.parseInt(value)); } catch (Exception ignored) {}
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> firstMap(Map<String, Object> row, String key)
    {
        Object value = row != null ? row.get(key) : null;
        if (value instanceof List)
        {
            List<?> list = (List<?>) value;
            if (!list.isEmpty() && list.get(0) instanceof Map)
                return (Map<String, Object>) list.get(0);
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private Integer firstInt(Map<String, Object> row, String key)
    {
        Object value = row != null ? row.get(key) : null;
        if (value instanceof List)
        {
            List<?> list = (List<?>) value;
            if (!list.isEmpty()) return parseInt(list.get(0));
        }
        return parseInt(value);
    }

    private int intVal(Map<String, Object> preferred, Map<String, Object> fallback, String key)
    {
        Integer value = preferred != null ? parseInt(preferred.get(key)) : null;
        if (value != null) return value;
        value = fallback != null ? parseInt(fallback.get(key)) : null;
        return value != null ? value : 0;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> map, String key)
    {
        if (map == null) return new ArrayList<>();
        Object value = map.get(key);
        if (value instanceof List) return (List<Map<String, Object>>) value;
        try
        {
            List<Map<String, Object>> result = om.convertValue(value, new TypeReference<List<Map<String, Object>>>() {});
            return result != null ? result : new ArrayList<>();
        }
        catch (Exception e) { return new ArrayList<>(); }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> getMap(Map<String, Object> map, String key)
    {
        Object value = map != null ? map.get(key) : null;
        return value instanceof Map ? (Map<String, Object>) value : null;
    }

    private String str(Map<String, Object> map, String key)
    {
        Object value = map != null ? map.get(key) : null;
        return value != null ? String.valueOf(value) : "";
    }

    private int getInt(Map<String, Object> map, String key)
    {
        Integer value = parseInt(map != null ? map.get(key) : null);
        return value != null ? value : 0;
    }

    private Integer intObj(Map<String, Object> map, String key)
    {
        return parseInt(map != null ? map.get(key) : null);
    }

    private Integer parseInt(Object value)
    {
        if (value instanceof Number) return ((Number) value).intValue();
        if (value != null)
        {
            try { return Integer.parseInt(value.toString()); } catch (Exception ignored) {}
        }
        return null;
    }
}
