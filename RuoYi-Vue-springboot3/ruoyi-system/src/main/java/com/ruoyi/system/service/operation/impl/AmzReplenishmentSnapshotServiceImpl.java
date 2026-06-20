package com.ruoyi.system.service.operation.impl;

import java.math.BigDecimal;
import java.util.*;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import com.ruoyi.system.domain.operation.AmzReplenishmentSnapshot;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.mapper.operation.AmzReplenishmentSnapshotMapper;
import com.ruoyi.system.service.operation.IAmzReplenishmentSnapshotService;
import com.ruoyi.system.service.operation.compute.AmzReplenishmentComputeService;

@Service
public class AmzReplenishmentSnapshotServiceImpl implements IAmzReplenishmentSnapshotService
{
    private static final Logger log = LoggerFactory.getLogger(AmzReplenishmentSnapshotServiceImpl.class);

    private static final Set<String> SORT_FIELDS = Set.of(
        "storeName", "sellerSku", "warehouseSku", "asin", "rating", "reviewCount",
        "adRate", "profitRate30d", "refundRate90d", "domesticStock", "pendingShipQty",
        "fbaStock", "fbaInbound", "totalInventory", "sales7d", "sales14d",
        "sales30d", "sales60d", "avgMonthlySales", "safetyStock", "shipQty",
        "replenishQty", "restockDays"
    );
    private static final Set<String> TEXT_FIELDS = Set.of(
        "storeName", "sellerSku", "warehouseSku", "asin", "principalName", "productCategory", "warehouseName"
    );
    private static final Map<String, String> NUM_MAP = new LinkedHashMap<>();
    static {
        NUM_MAP.put("rating","rating"); NUM_MAP.put("reviewCount","review_count");
        NUM_MAP.put("adRate","ad_rate"); NUM_MAP.put("profitRate30d","profit_rate_30d");
        NUM_MAP.put("refundRate90d","refund_rate_90d"); NUM_MAP.put("purchasedQty","purchased_qty");
        NUM_MAP.put("domesticStock","domestic_stock"); NUM_MAP.put("pendingShipQty","pending_ship_qty");
        NUM_MAP.put("fbaStock","fba_stock"); NUM_MAP.put("fbaInbound","fba_inbound");
        NUM_MAP.put("totalInventory","total_inventory"); NUM_MAP.put("sales7d","sales_7d");
        NUM_MAP.put("sales14d","sales_14d"); NUM_MAP.put("sales30d","sales_30d");
        NUM_MAP.put("sales60d","sales_60d"); NUM_MAP.put("avgMonthlySales","avg_monthly_sales");
        NUM_MAP.put("safetyStock","safety_stock"); NUM_MAP.put("shipQty","ship_qty");
        NUM_MAP.put("replenishQty","replenish_qty"); NUM_MAP.put("restockDays","restock_days");
    }
    private static final Set<String> DISTINCT_COLS = Set.of(
        "store_name","seller_sku","warehouse_sku","asin","principal_name","product_category","warehouse_name"
    );

    @Autowired private AmzReplenishmentSnapshotMapper mapper;
    @Autowired private AmzReplenishmentComputeService computeService;

    @Override
    public List<AmzReplenishmentSnapshot> selectAmzReplenishmentSnapshotList(AmzReplenishmentSnapshot snap)
    {
        normalizeSort(snap);
        return mapper.selectAmzReplenishmentSnapshotList(snap);
    }

    @Override
    public List<AmzReplenishmentSnapshot> search(EbayReplenishmentSearchRequest req)
    {
        return mapper.search(buildParams(req));
    }

    @Override
    public List<String> distinctValues(String field, String keyword)
    {
        if (field == null || !DISTINCT_COLS.contains(field)) return Collections.emptyList();
        return mapper.selectDistinctValues(field, keyword != null ? keyword.trim() : null);
    }

    @Override
    @Transactional
    public int refreshSnapshot()
    {
        log.info("==== AMZ补货快照刷新 开始 ====");
        long t = System.currentTimeMillis();
        mapper.deleteAll();
        int rows = mapper.insertByListing();
        log.info("==== AMZ补货快照刷新 完成: {} 条 耗时{}ms ====", rows, System.currentTimeMillis() - t);
        return rows;
    }

    private Map<String, Object> buildParams(EbayReplenishmentSearchRequest req)
    {
        Map<String, Object> p = new HashMap<>();
        if (req.getSortField() != null && SORT_FIELDS.contains(req.getSortField()))
        {
            p.put("sortField", req.getSortField());
            p.put("sortOrder", "ascending".equals(req.getSortOrder()) ? "ascending" : "descending");
        }
        if (req.getFilters() == null || req.getFilters().isEmpty()) return p;
        for (EbayReplenishmentSearchRequest.FilterItem f : req.getFilters())
        {
            if (!StringUtils.hasText(f.getField()) || !StringUtils.hasText(f.getValue())) continue;
            String field = f.getField().trim(), raw = f.getValue().trim();
            if (TEXT_FIELDS.contains(field)) { p.put(field, raw); continue; }
            if (NUM_MAP.containsKey(field)) parseNum(p, field, raw);
        }
        return p;
    }

    private void parseNum(Map<String, Object> p, String field, String raw)
    {
        String op, ns;
        if (raw.startsWith(">=")) { op = ">="; ns = raw.substring(2).trim(); }
        else if (raw.startsWith("<=")) { op = "<="; ns = raw.substring(2).trim(); }
        else if (raw.startsWith(">")) { op = ">"; ns = raw.substring(1).trim(); }
        else if (raw.startsWith("<")) { op = "<"; ns = raw.substring(1).trim(); }
        else if (raw.startsWith("=")) { op = "="; ns = raw.substring(1).trim(); }
        else { op = "="; ns = raw; }
        if (ns.isEmpty()) return;
        try { p.put(field + "_op", op); p.put(field + "_val", BigDecimal.valueOf(Double.parseDouble(ns))); }
        catch (NumberFormatException e) { p.put(field, raw); }
    }

    private void normalizeSort(AmzReplenishmentSnapshot s)
    {
        if (s.getSortField() == null || !SORT_FIELDS.contains(s.getSortField())) { s.setSortField(null); s.setSortOrder(null); }
        else if (!"ascending".equals(s.getSortOrder())) { s.setSortOrder("descending"); }
    }
}
