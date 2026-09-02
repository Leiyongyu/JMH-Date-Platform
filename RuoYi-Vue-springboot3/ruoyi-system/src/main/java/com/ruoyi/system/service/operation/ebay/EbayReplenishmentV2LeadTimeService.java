package com.ruoyi.system.service.operation.ebay;

import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.ebay.EbayReplenishmentV2LeadTime;
import com.ruoyi.system.domain.operation.ebay.EbayReplenishmentV2LeadTimeSaveRequest;
import com.ruoyi.system.mapper.operation.ebay.EbayReplenishmentV2LeadTimeMapper;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/** eBay补货2.0人工时效配置服务。 */
@Service
public class EbayReplenishmentV2LeadTimeService
{
    public static final String FIELD_CHENGDU_WAREHOUSE =
            "chengduWarehouseToWarehouseDays";
    public static final String FIELD_CHENGDU_QC_OUTBOUND =
            "chengduQcOutboundDays";
    public static final String FIELD_OVERSEAS_LISTING =
            "overseasTransitToListingDays";

    private static final int MAX_DAYS = 3650;
    private final EbayReplenishmentV2LeadTimeMapper mapper;

    public EbayReplenishmentV2LeadTimeService(
            EbayReplenishmentV2LeadTimeMapper mapper)
    {
        this.mapper = mapper;
    }

    /**
     * 将独立保存的人工时效批量合并到Python返回的当前页数据中。
     * 只读取当前页的站点和完整SKU，不参与订单、库存等源数据刷新。
     */
    public Object enrich(Object data)
    {
        if (!(data instanceof Map<?, ?> dataMap)) return data;
        Object itemsValue = dataMap.get("items");
        if (!(itemsValue instanceof List<?> items) || items.isEmpty()) return data;

        Map<SiteSkuKey, EbayReplenishmentV2LeadTime> requested =
                new LinkedHashMap<>();
        for (Object value : items)
        {
            if (!(value instanceof Map<?, ?> item)) continue;
            String site = text(item.get("site"));
            if (site == null) site = text(item.get("site_name"));
            String sku = text(item.get("sku"));
            if (sku == null) sku = text(item.get("inventory_sku"));
            if (site == null || sku == null) continue;

            SiteSkuKey key = new SiteSkuKey(site, sku);
            requested.computeIfAbsent(key, ignored -> key.toDomain());
        }
        if (requested.isEmpty()) return data;

        List<EbayReplenishmentV2LeadTime> configs =
                mapper.selectByKeys(List.copyOf(requested.values()));
        Map<SiteSkuKey, EbayReplenishmentV2LeadTime> byKey =
                new LinkedHashMap<>();
        for (EbayReplenishmentV2LeadTime config : configs)
        {
            byKey.put(new SiteSkuKey(config.getSite(), config.getSku()), config);
        }

        for (Object value : items)
        {
            if (!(value instanceof Map<?, ?> rawItem)) continue;
            Map<String, Object> item = mutableMap(rawItem);
            String site = text(item.get("site"));
            if (site == null) site = text(item.get("site_name"));
            String sku = text(item.get("sku"));
            if (sku == null) sku = text(item.get("inventory_sku"));
            EbayReplenishmentV2LeadTime config =
                    site == null || sku == null
                    ? null : byKey.get(new SiteSkuKey(site, sku));

            item.put("chengdu_warehouse_to_warehouse_days",
                    config == null ? null
                            : config.getChengduWarehouseToWarehouseDays());
            item.put("chengdu_qc_outbound_days",
                    config == null ? null : config.getChengduQcOutboundDays());
            item.put("overseas_transit_to_listing_days",
                    config == null ? null
                            : config.getOverseasTransitToListingDays());
        }
        return data;
    }

    /** 单字段保存，防止多人同时维护不同字段时互相覆盖。 */
    @Transactional(rollbackFor = Exception.class)
    public void save(EbayReplenishmentV2LeadTimeSaveRequest request,
                     String operator)
    {
        if (request == null) throw new ServiceException("人工时效参数不能为空");
        String site = requiredText(request.getSite(), "站点不能为空", 100);
        String sku = requiredText(request.getSku(), "SKU不能为空", 255);
        String field = normalizeField(request.getField());
        Integer days = request.getDays();
        if (days != null && (days < 0 || days > MAX_DAYS))
        {
            throw new ServiceException("时效天数必须是0到3650之间的整数");
        }
        mapper.upsertField(site, sku, field, days, safeOperator(operator));
    }

    private String normalizeField(String value)
    {
        String field = text(value);
        if (FIELD_CHENGDU_WAREHOUSE.equals(field)
                || FIELD_CHENGDU_QC_OUTBOUND.equals(field)
                || FIELD_OVERSEAS_LISTING.equals(field))
        {
            return field;
        }
        throw new ServiceException("人工时效字段不正确");
    }

    private String requiredText(String value, String message, int maxLength)
    {
        String result = text(value);
        if (result == null) throw new ServiceException(message);
        if (result.length() > maxLength)
        {
            throw new ServiceException(message.replace("不能为空", "长度超出限制"));
        }
        return result;
    }

    private String safeOperator(String value)
    {
        String result = text(value);
        if (result == null) return "SYSTEM";
        return result.length() <= 64 ? result : result.substring(0, 64);
    }

    private String text(Object value)
    {
        if (value == null) return null;
        String result = String.valueOf(value).trim();
        return StringUtils.hasText(result) ? result : null;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mutableMap(Map<?, ?> value)
    {
        return (Map<String, Object>) value;
    }

    private record SiteSkuKey(String site, String sku)
    {
        private EbayReplenishmentV2LeadTime toDomain()
        {
            EbayReplenishmentV2LeadTime result =
                    new EbayReplenishmentV2LeadTime();
            result.setSite(site);
            result.setSku(sku);
            return result;
        }
    }
}
