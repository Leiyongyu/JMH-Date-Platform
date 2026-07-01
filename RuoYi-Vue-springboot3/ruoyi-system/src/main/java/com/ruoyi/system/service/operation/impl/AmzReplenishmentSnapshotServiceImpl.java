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
import com.ruoyi.system.domain.operation.AmzSalesBreakdownRequest;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.mapper.operation.AmzReplenishmentSnapshotMapper;
import com.ruoyi.system.service.operation.IAmzReplenishmentSnapshotService;
import com.ruoyi.system.service.operation.compute.AmzReplenishmentComputeService;

@Service
public class AmzReplenishmentSnapshotServiceImpl implements IAmzReplenishmentSnapshotService
{
    private static final Logger log = LoggerFactory.getLogger(AmzReplenishmentSnapshotServiceImpl.class);

    private static final Set<String> SORT_FIELDS = Set.of(
        "storeName", "sellerSku", "warehouseSku", "asin", "price", "rating", "reviewCount",
        "adRate", "profitRate30d", "refundRate90d", "domesticStock", "pendingShipQty",
        "fbaStock", "fbaInbound", "totalInventory", "sales7d", "sales14d",
        "sales30d", "sales60d", "salesSpeed14d", "salesSpeed30d", "salesSpeed60d",
        "avgMonthlySales", "safetyStock", "shipQty", "replenishQty", "restockDays"
    );
    private static final Set<String> TEXT_FIELDS = Set.of(
        "storeName", "storeNameExclude", "sellerSku", "warehouseSku", "asin", "principalName", "productCategory", "warehouseName",
        "regionGroup"
    );
    private static final Map<String, String> NUM_MAP = new LinkedHashMap<>();
    static {
        NUM_MAP.put("rating","rating"); NUM_MAP.put("reviewCount","review_count");
        NUM_MAP.put("price","price");
        NUM_MAP.put("adRate","ad_rate"); NUM_MAP.put("profitRate30d","profit_rate_30d");
        NUM_MAP.put("refundRate90d","refund_rate_90d"); NUM_MAP.put("purchasedQty","purchased_qty");
        NUM_MAP.put("domesticStock","domestic_stock"); NUM_MAP.put("pendingShipQty","pending_ship_qty");
        NUM_MAP.put("fbaStock","fba_stock"); NUM_MAP.put("fbaInbound","fba_inbound");
        NUM_MAP.put("totalInventory","total_inventory"); NUM_MAP.put("sales7d","sales_7d");
        NUM_MAP.put("sales14d","sales_14d"); NUM_MAP.put("sales30d","sales_30d");
        NUM_MAP.put("sales60d","sales_60d"); NUM_MAP.put("salesSpeed14d","sales_speed_14d");
        NUM_MAP.put("salesSpeed30d","sales_speed_30d"); NUM_MAP.put("salesSpeed60d","sales_speed_60d");
        NUM_MAP.put("avgMonthlySales","avg_monthly_sales");
        NUM_MAP.put("safetyStock","safety_stock"); NUM_MAP.put("shipQty","ship_qty");
        NUM_MAP.put("replenishQty","replenish_qty"); NUM_MAP.put("restockDays","restock_days");
    }
    private static final Set<String> ALLOWED_OPS = Set.of("=", ">", ">=", "<", "<=", "between", "isNull", "isNotNull");
    private static final Map<String, String> FIELD_TO_COL = Map.ofEntries(
        Map.entry("storeName","store_name"), Map.entry("sellerSku","seller_sku"),
        Map.entry("warehouseSku","warehouse_sku"), Map.entry("asin","asin"),
        Map.entry("principalName","principal_name"), Map.entry("productCategory","product_category"),
        Map.entry("warehouseName","warehouse_name"),
        Map.entry("sales7d","sales_7d"), Map.entry("sales14d","sales_14d"), Map.entry("sales30d","sales_30d"),
        Map.entry("sales60d","sales_60d"),
        Map.entry("salesSpeed14d","sales_speed_14d"), Map.entry("salesSpeed30d","sales_speed_30d"),
        Map.entry("salesSpeed60d","sales_speed_60d"), Map.entry("avgMonthlySales","avg_monthly_sales")
    );
    private static final Set<String> ALLOWED_FIELDS = FIELD_TO_COL.keySet();

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
        String col = FIELD_TO_COL.get(field);
        if (col == null) return Collections.emptyList();
        return mapper.selectDistinctValues(col, keyword != null ? keyword.trim() : null);
    }

    @Override
    public List<Map<String, Object>> salesBreakdown(String warehouseSku, String field, List<String> storeNames)
    {
        String col = FIELD_TO_COL.get(field);
        if (col == null) return Collections.emptyList();
        return mapper.selectSalesBreakdown(warehouseSku, col, storeNames);
    }

    @Override
    public List<Map<String, Object>> salesBreakdown(AmzSalesBreakdownRequest req)
    {
        if (req == null || !StringUtils.hasText(req.getWarehouseSku())) return Collections.emptyList();
        String col = FIELD_TO_COL.get(req.getField());
        if (col == null) return Collections.emptyList();
        Map<String, Object> params = buildParams(req);
        params.put("warehouseSkuExact", req.getWarehouseSku().trim());
        params.put("breakdownColumn", col);
        return mapper.selectSalesBreakdownByFilters(params);
    }

    @Override
    @Transactional
    public int refreshSnapshot()
    {
        log.info("==== AMZ补货快照刷新 开始 ====");
        long t = System.currentTimeMillis();
        String batchNo = newBatchNo("AMZ_REPL");
        int rows = mapper.insertByListing(batchNo);
        if (rows <= 0)
        {
            log.warn("==== AMZ replenishment snapshot refresh returned empty result, keep current snapshot ====");
            return 0;
        }
        mapper.activateBatch(batchNo);
        mapper.deleteNonCurrent();
        log.info("==== AMZ补货快照刷新 完成: {} 条 耗时{}ms ====", rows, System.currentTimeMillis() - t);
        return rows;
    }

    private String newBatchNo(String prefix)
    {
        return prefix + "-" + System.currentTimeMillis();
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
            if (!StringUtils.hasText(f.getField())) continue;
            String field = f.getField().trim();
            if (TEXT_FIELDS.contains(field))
            {
                if (!StringUtils.hasText(f.getValue())) continue;
                p.put(field, f.getValue().trim());
                continue;
            }
            if (NUM_MAP.containsKey(field)) parseNum(p, field, f);
        }
        return p;
    }

    private void parseNum(Map<String, Object> p, String field, EbayReplenishmentSearchRequest.FilterItem f)
    {
        String operator = f.getOperator();
        String value = f.getValue();
        String value2 = f.getValue2();
        // mapper XML 用 DB 列名做参数键（如 review_count_op），不是前端字段名（如 reviewCount_op）
        String db = NUM_MAP.getOrDefault(field, field);

        // 新格式：结构化 operator
        if (StringUtils.hasText(operator) && ALLOWED_OPS.contains(operator))
        {
            if ("isNull".equals(operator)) { p.put(db + "_op", "isNull"); return; }
            if ("isNotNull".equals(operator)) { p.put(db + "_op", "isNotNull"); return; }
            if ("between".equals(operator) && StringUtils.hasText(value) && StringUtils.hasText(value2))
            {
                try {
                    p.put(db + "_op", "between");
                    p.put(db + "_val", new BigDecimal(value.trim()));
                    p.put(db + "_val2", new BigDecimal(value2.trim()));
                } catch (NumberFormatException ignored) {}
                return;
            }
            if (StringUtils.hasText(value))
            {
                try {
                    p.put(db + "_op", operator);
                    p.put(db + "_val", new BigDecimal(value.trim()));
                } catch (NumberFormatException ignored) {}
                return;
            }
            return;
        }

        // 旧格式兼容：value=">30"
        if (!StringUtils.hasText(value)) return;
        String raw = value.trim();
        String op, ns;
        if (raw.startsWith(">=")) { op = ">="; ns = raw.substring(2).trim(); }
        else if (raw.startsWith("<=")) { op = "<="; ns = raw.substring(2).trim(); }
        else if (raw.startsWith(">")) { op = ">"; ns = raw.substring(1).trim(); }
        else if (raw.startsWith("<")) { op = "<"; ns = raw.substring(1).trim(); }
        else if (raw.startsWith("=")) { op = "="; ns = raw.substring(1).trim(); }
        else { op = "="; ns = raw; }
        if (ns.isEmpty()) return;
        try { p.put(db + "_op", op); p.put(db + "_val", BigDecimal.valueOf(Double.parseDouble(ns))); }
        catch (NumberFormatException e) { p.put(field, raw); }
    }

    private void normalizeSort(AmzReplenishmentSnapshot s)
    {
        if (s.getSortField() == null || !SORT_FIELDS.contains(s.getSortField())) { s.setSortField(null); s.setSortOrder(null); }
        else if (!"ascending".equals(s.getSortOrder())) { s.setSortOrder("descending"); }
    }
}
