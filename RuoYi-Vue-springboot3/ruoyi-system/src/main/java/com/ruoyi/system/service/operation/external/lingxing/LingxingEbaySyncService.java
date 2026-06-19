package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.domain.operation.external.EbayProductListing;
import com.ruoyi.system.mapper.operation.external.EbayProductDedupMapper;
import com.ruoyi.system.mapper.operation.external.EbayProductListingMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * 领星 eBay 商品刊登同步 —— 分页拉取并按 item_id upsert 到 ebay_product_listing，
 * 完成后触发重建 ebay_product_dedup 去重表。
 */
@Service
public class LingxingEbaySyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(LingxingEbaySyncService.class);
    private static final String API_PATH = "basicOpen/multiplatform/ebay/list";
    private static final DateTimeFormatter DT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final LingxingGatewayService gateway;
    private final EbayProductListingMapper mapper;
    private final ObjectMapper objectMapper;

    public LingxingEbaySyncService(LingxingGatewayService gateway,
                                    EbayProductListingMapper mapper,
                                    ObjectMapper objectMapper)
    {
        this.gateway = gateway;
        this.mapper = mapper;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public OperationSyncResult syncAll() throws Exception
    {
        long start = System.currentTimeMillis();
        int inserted = 0, updated = 0, remoteTotal = 0;
        int offset = 0, pageSize = 200;

        for (int guard = 0; guard < 10000; guard++)
        {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("offset", offset);
            body.put("length", pageSize);
            Map<String, Object> resp = gateway.post(API_PATH, body);
            List<Map<String, Object>> data = getList(resp, "data");
            if (data.isEmpty()) break;

            remoteTotal = Math.max(remoteTotal, getInt(resp, "total"));
            int[] stats = upsertBatch(data);
            inserted += stats[0];
            updated += stats[1];

            if (data.size() < pageSize) break;
            offset += pageSize;
            if (remoteTotal > 0 && offset >= remoteTotal) break;
        }

        // 重建去重表
        int dedupCount = 0;
        try
        {
            EbayProductDedupMapper dedupMapper = SpringUtils.getBean(EbayProductDedupMapper.class);
            dedupCount = dedupMapper.rebuildFromListing();
            LOG.info("eBay去重表重建完成: {}条", dedupCount);
        }
        catch (Exception e) { LOG.warn("重建去重表失败: {}", e.getMessage()); }

        long elapsed = System.currentTimeMillis() - start;
        return OperationSyncResult.success("ebay_listing", "领星-eBay商品刊登", API_PATH,
                remoteTotal, inserted + updated, elapsed);
    }

    private int[] upsertBatch(List<Map<String, Object>> items)
    {
        List<String> itemIds = new ArrayList<>();
        for (Map<String, Object> item : items)
        {
            String id = getString(item, "item_id", "itemId");
            if (StringUtils.hasText(id)) itemIds.add(id);
        }
        if (itemIds.isEmpty()) return new int[]{0, 0};

        Map<String, EbayProductListing> existing = new HashMap<>();
        for (EbayProductListing e : mapper.selectByItemIds(itemIds))
            if (e.getItemId() != null) existing.put(e.getItemId(), e);

        int inserted = 0, updated = 0;
        List<EbayProductListing> toInsert = new ArrayList<>();
        List<EbayProductListing> toUpdate = new ArrayList<>();

        for (Map<String, Object> item : items)
        {
            String itemId = getString(item, "item_id", "itemId");
            if (!StringUtils.hasText(itemId)) continue;

            EbayProductListing e = existing.get(itemId);
            boolean isNew = (e == null);
            if (isNew) { e = new EbayProductListing(); e.setPlatform("eBay"); e.setItemId(itemId); }

            e.setItemUrl(getString(item, "item_url", "itemUrl"));
            e.setPictureUrl(getString(item, "picture_url", "pictureUrl"));
            String msku = getString(item, "msku"); e.setMsku(msku);
            e.setSku(extractBaseSku(msku != null ? msku : ""));
            e.setLocalSku(getString(item, "local_sku", "localSku"));
            e.setTitle(getString(item, "title"));
            e.setLocalName(getString(item, "local_name", "localName"));
            e.setAttribute(getString(item, "attribute"));
            e.setListingType(getIntObj(item, "listing_type", "listingType"));
            e.setListingTypeName(getString(item, "listing_type_name", "listingTypeName"));
            e.setListingStatus(getIntObj(item, "listing_status", "listingStatus"));
            e.setListingStatusName(getString(item, "listing_status_name", "listingStatusName"));
            e.setPrice(getDecimal(item, "price"));
            e.setStartPrice(getDecimal(item, "start_price", "startPrice"));
            e.setAcceptPrice(getDecimal(item, "accept_price", "acceptPrice"));
            e.setQuantity(getIntObj(item, "quantity"));
            e.setAutoRestock(getIntObj(item, "auto_restock", "autoRestock"));
            e.setLocation(getString(item, "location"));
            e.setDispatchTimeMax(getIntObj(item, "dispatch_time_max", "dispatchTimeMax"));
            e.setListingStartTime(parseDt(getString(item, "listing_start_time", "listingStartTime")));
            e.setListingEndTime(parseDt(getString(item, "listing_end_time", "listingEndTime")));
            e.setStoreId(getString(item, "store_id", "storeId"));
            e.setStoreName(getString(item, "store_name", "storeName"));
            e.setSiteCode(getString(item, "site_code", "siteCode"));
            e.setSiteName(getString(item, "site_name", "siteName"));

            if (isNew) { toInsert.add(e); inserted++; }
            else { toUpdate.add(e); updated++; }
        }

        if (!toInsert.isEmpty()) mapper.batchInsert(toInsert);
        for (EbayProductListing e : toUpdate) mapper.updateByItemId(e);
        return new int[]{inserted, updated};
    }

    // ---- helpers ----
    private String extractBaseSku(String msku)
    {
        if (msku == null || msku.isEmpty()) return "";
        String[] parts = msku.split("-");
        if (parts.length < 2) return msku;
        if (parts[0].matches("\\d+PC") && parts.length >= 3)
            return parts[0] + "-" + parts[1] + "-" + parts[2];
        return parts[0] + "-" + parts[1];
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> getList(Map<String, Object> resp, String key)
    {
        Object o = resp.get(key);
        if (o instanceof List) return (List<Map<String, Object>>) o;
        try { return objectMapper.convertValue(o, new TypeReference<List<Map<String, Object>>>() {}); }
        catch (Exception e) { return new ArrayList<>(); }
    }

    private String getString(Map<String, Object> m, String... keys)
    {
        for (String k : keys) { Object v = m.get(k); if (v != null && StringUtils.hasText(v.toString())) return v.toString(); }
        return null;
    }

    private Integer getIntObj(Map<String, Object> m, String... keys)
    {
        String s = getString(m, keys); if (s == null) return null;
        try { return Integer.valueOf(s); } catch (Exception e) { return null; }
    }

    private int getInt(Map<String, Object> m, String key)
    {
        Object v = m.get(key);
        if (v instanceof Number) return ((Number) v).intValue();
        if (v != null) try { return Integer.parseInt(v.toString()); } catch (Exception e) {}
        return 0;
    }

    private BigDecimal getDecimal(Map<String, Object> m, String... keys)
    {
        String s = getString(m, keys); if (s == null) return null;
        try { return new BigDecimal(s); } catch (Exception e) { return null; }
    }

    private LocalDateTime parseDt(String v)
    {
        if (!StringUtils.hasText(v)) return null;
        try { return LocalDateTime.parse(v, DT); } catch (Exception e) { return null; }
    }
}
