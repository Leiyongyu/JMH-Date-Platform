package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.ShopList;
import com.ruoyi.system.mapper.operation.external.ShopListMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * 领星多平台店铺同步服务 —— 使用 v2 统一接口一次拉取 eBay+Amazon 店铺。
 * API: POST /pb/mp/shop/v2/getSellerList
 *
 * @author JMH
 */
@Service
public class LingxingShopSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(LingxingShopSyncService.class);
    private static final String API_PATH = "pb/mp/shop/v2/getSellerList";

    /** 需要同步的平台 */
    private static final List<Integer> PLATFORM_CODES = Arrays.asList(10003, 10001); // eBay, Amazon

    private final LingxingGatewayService gateway;
    private final ShopListMapper shopListMapper;
    private final ObjectMapper objectMapper;

    public LingxingShopSyncService(LingxingGatewayService gateway,
                                    ShopListMapper shopListMapper,
                                    ObjectMapper objectMapper)
    {
        this.gateway = gateway;
        this.shopListMapper = shopListMapper;
        this.objectMapper = objectMapper;
    }

    /**
     * 一次请求拉取所有平台店铺，增量 upsert 到 shop_list。
     */
    @Transactional
    public OperationSyncResult syncShops() throws Exception
    {
        long start = System.currentTimeMillis();
        List<OperationSyncResult.FailureItem> failures = new ArrayList<>();
        int totalInserted = 0, totalUpdated = 0, totalRemote = 0;

        int offset = 0;
        int length = 200;

        while (true)
        {
            Map<String, Object> resp;
            try
            {
                resp = fetchShops(offset, length);
            }
            catch (Exception e)
            {
                LOG.error("拉取店铺列表失败 offset={}: {}", offset, e.getMessage());
                failures.add(new OperationSyncResult.FailureItem(
                        "offset=" + offset, e.getMessage()));
                break;
            }

            List<Map<String, Object>> data = getDataList(resp);
            if (data.isEmpty()) break;

            totalRemote += data.size();
            int[] stats = upsertShops(data);
            totalInserted += stats[0];
            totalUpdated += stats[1];

            // 返回值不够一页说明到底了
            Object totalObj = resp.get("total");
            if (totalObj instanceof Number && data.size() < length) break;
            if (data.size() < length) break;
            offset += length;
        }

        long elapsed = System.currentTimeMillis() - start;
        int totalSuccess = totalInserted + totalUpdated;

        if (!failures.isEmpty() && totalSuccess == 0)
        {
            return OperationSyncResult.failed("shop_list", "领星-多平台店铺", API_PATH,
                    "所有分页同步失败", elapsed);
        }
        if (!failures.isEmpty())
        {
            return OperationSyncResult.partial("shop_list", "领星-多平台店铺", API_PATH,
                    totalRemote, totalSuccess, failures.size(), failures, elapsed);
        }
        return OperationSyncResult.success("shop_list", "领星-多平台店铺", API_PATH,
                totalRemote, totalSuccess, elapsed);
    }

    // ========== 内部方法 ==========

    private Map<String, Object> fetchShops(int offset, int length) throws Exception
    {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("offset", offset);
        body.put("length", length);
        body.put("platform_code", PLATFORM_CODES); // [10003, 10001]
        body.put("is_sync", 1);
        body.put("status", 1);

        LOG.info("请求店铺列表: offset={}, length={}, platforms={}", offset, length, PLATFORM_CODES);
        Map<String, Object> resp = gateway.post(API_PATH, body);
        LOG.info("店铺列表 API 响应: code={}, msg={}, data是否为null={}",
                resp.get("code"), resp.get("msg"), resp.get("data") == null);
        return resp;
    }

    /** 批量 upsert，返回 [inserted, updated] */
    private int[] upsertShops(List<Map<String, Object>> rows)
    {
        // 1. 收集所有 (platform_code, store_id) 联合键
        List<ShopListMapper.ShopListKey> keys = new ArrayList<>();
        for (Map<String, Object> row : rows)
        {
            String platformCode = getString(row, "platform_code", "platformCode");
            String storeId = getString(row, "store_id", "storeId");
            if (platformCode != null && storeId != null)
            {
                keys.add(new ShopListMapper.ShopListKey(platformCode, storeId));
            }
        }
        if (keys.isEmpty()) return new int[]{0, 0};

        // 2. 批量查已有记录
        Map<String, ShopList> existing = new HashMap<>();
        for (ShopList s : shopListMapper.selectByKeys(keys))
        {
            existing.put(s.getPlatformCode() + ":" + s.getStoreId(), s);
        }

        // 3. 区分新增/更新
        int inserted = 0, updated = 0;
        List<ShopList> toInsert = new ArrayList<>();
        List<ShopList> toUpdate = new ArrayList<>();

        for (Map<String, Object> row : rows)
        {
            String platformCode = getString(row, "platform_code", "platformCode");
            String storeId = getString(row, "store_id", "storeId");
            if (platformCode == null || storeId == null) continue;

            // 跳过未启用的
            Integer status = getIntObj(row, "status");
            if (status != null && status != 1) continue;

            String key = platformCode + ":" + storeId;
            ShopList entity = existing.get(key);
            boolean isNew = (entity == null);
            if (isNew)
            {
                entity = new ShopList();
                entity.setPlatformCode(platformCode);
                entity.setStoreId(storeId);
            }

            entity.setSid(getString(row, "sid"));
            entity.setStoreName(getString(row, "store_name", "storeName"));
            entity.setPlatformName(getString(row, "platform_name", "platformName"));
            entity.setCurrency(getString(row, "currency"));
            entity.setIsSync(getIntObj(row, "is_sync", "isSync"));
            entity.setStatus(status != null ? status : 1);
            entity.setCountryCode(getString(row, "country_code", "countryCode"));

            if (isNew)
            {
                toInsert.add(entity);
                inserted++;
            }
            else
            {
                toUpdate.add(entity);
                updated++;
            }
        }

        // 4. 批量写入
        if (!toInsert.isEmpty()) shopListMapper.batchInsert(toInsert);
        for (ShopList s : toUpdate) shopListMapper.updateById(s);

        LOG.info("店铺同步结果: 新增{}条, 更新{}条", inserted, updated);
        return new int[]{inserted, updated};
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getDataList(Map<String, Object> resp)
    {
        if (resp == null) return new ArrayList<>();
        Object data = resp.get("data");
        if (data == null) return new ArrayList<>();
        if (data instanceof List) return (List<Map<String, Object>>) data;
        try
        {
            List<Map<String, Object>> converted = objectMapper.convertValue(data,
                    new TypeReference<List<Map<String, Object>>>() {});
            return converted != null ? converted : new ArrayList<>();
        }
        catch (Exception e)
        {
            LOG.warn("解析店铺 data 字段失败: {}", e.getMessage());
            return new ArrayList<>();
        }
    }

    private String getString(Map<String, Object> map, String... keys)
    {
        for (String k : keys)
        {
            Object v = map.get(k);
            if (v != null && StringUtils.hasText(String.valueOf(v)))
                return String.valueOf(v);
        }
        return null;
    }

    private Integer getIntObj(Map<String, Object> map, String... keys)
    {
        String s = getString(map, keys);
        if (s == null) return null;
        try { return Integer.valueOf(s); }
        catch (Exception e) { return null; }
    }
}
