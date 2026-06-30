package com.ruoyi.system.service.operation.impl;

import java.math.BigDecimal;
import java.util.*;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;
import com.ruoyi.system.mapper.operation.EbayReplenishmentSnapshotMapper;
import com.ruoyi.system.service.operation.IEbayReplenishmentSnapshotService;
import com.ruoyi.system.service.operation.compute.EbayReplenishmentComputeService;

@Service
public class EbayReplenishmentSnapshotServiceImpl implements IEbayReplenishmentSnapshotService
{
    private static final Logger log = LoggerFactory.getLogger(EbayReplenishmentSnapshotServiceImpl.class);

    // ---- 白名单 ----
    private static final Set<String> SORT_FIELDS = Set.of(
        "site", "sku", "skuLevel", "profitRate30d", "returnRate",
        "overseasOnway", "overseasSellable", "overseasTotal", "purchasePendingDelivery",
        "localSellable", "localOnway", "purchasePlanQty", "lockedQty", "totalInventory",
        "sales7d", "sales30d", "sales90d", "maxMonthlySales",
        "overseasSellableSalesRatio", "overseasTotalSalesRatio", "totalInventorySalesRatio",
        "outboundDays", "purchaseCycleDays", "suggestPurchaseQty", "maxMonthlyReplenishQty"
    );

    /** 允许文本筛选的列 */
    private static final Set<String> TEXT_FIELDS = Set.of(
        "site", "sku", "productName", "skuLevel", "ownerName", "lastLocalOutboundTime",
        "productNature", "returnLevel"
    );

    /** 允许的操作符白名单 */
    private static final Set<String> ALLOWED_OPS = Set.of(
        "=", ">", ">=", "<", "<=", "between", "isNull", "isNotNull"
    );

    /** 允许数值筛选的列 → SQL 列名 */
    private static final Map<String, String> NUMERIC_FIELD_MAP = new LinkedHashMap<>();
    static {
        NUMERIC_FIELD_MAP.put("overseasOnway",          "overseas_onway");
        NUMERIC_FIELD_MAP.put("overseasSellable",       "overseas_sellable");
        NUMERIC_FIELD_MAP.put("overseasTotal",          "overseas_total");
        NUMERIC_FIELD_MAP.put("totalInventory",         "total_inventory");
        NUMERIC_FIELD_MAP.put("sales7d",                "sales_7d");
        NUMERIC_FIELD_MAP.put("sales30d",               "sales_30d");
        NUMERIC_FIELD_MAP.put("sales90d",               "sales_90d");
        NUMERIC_FIELD_MAP.put("maxMonthlySales",        "max_monthly_sales");
        NUMERIC_FIELD_MAP.put("localSellable",          "local_sellable");
        NUMERIC_FIELD_MAP.put("localOnway",             "local_onway");
        NUMERIC_FIELD_MAP.put("lockedQty",              "locked_qty");
        NUMERIC_FIELD_MAP.put("purchasePendingDelivery","purchase_pending_delivery");
        NUMERIC_FIELD_MAP.put("purchasePlanQty",        "purchase_plan_qty");
        NUMERIC_FIELD_MAP.put("outboundDays",           "outbound_days");
        NUMERIC_FIELD_MAP.put("purchaseCycleDays",      "purchase_cycle_days");
        NUMERIC_FIELD_MAP.put("suggestPurchaseQty",     "suggest_purchase_qty");
        NUMERIC_FIELD_MAP.put("maxMonthlyReplenishQty", "max_monthly_replenish_qty");
        NUMERIC_FIELD_MAP.put("profitRate30d",          "profit_rate_30d");
        NUMERIC_FIELD_MAP.put("returnRate",             "return_rate");
        NUMERIC_FIELD_MAP.put("monthlyTurnoverRate",   "monthly_turnover_rate");
        NUMERIC_FIELD_MAP.put("overseasSellableSalesRatio", "overseas_sellable_sales_ratio");
        NUMERIC_FIELD_MAP.put("overseasTotalSalesRatio",    "overseas_total_sales_ratio");
        NUMERIC_FIELD_MAP.put("totalInventorySalesRatio",   "total_inventory_sales_ratio");
    }

    /** 百分比字段（前端*100显示，DB 存原值），筛选时需 /100 */
    private static final Set<String> PERCENT_FIELDS = Set.of(
        "returnRate", "overseasSellableSalesRatio", "overseasTotalSalesRatio", "totalInventorySalesRatio"
    );

    /** 允许 distinct 的列（白名单） */
    private static final Set<String> DISTINCT_FIELDS = Set.of(
        "site", "sku_level", "owner_name", "product_name", "sku"
    );

    @Autowired
    private EbayReplenishmentSnapshotMapper snapshotMapper;

    @Autowired
    private EbayReplenishmentComputeService computeService;

    // ========================================================================
    // 基础查询（保留若依兼容）
    // ========================================================================

    @Override
    public List<EbayReplenishmentSnapshot> selectEbayReplenishmentSnapshotList(EbayReplenishmentSnapshot snapshot)
    {
        normalizeSort(snapshot);
        return snapshotMapper.selectEbayReplenishmentSnapshotList(snapshot);
    }

    // ========================================================================
    // 新版搜索：前端 filters[] → 解析 → SQL WHERE（不再内存过滤）
    // ========================================================================

    @Override
    public List<EbayReplenishmentSnapshot> search(EbayReplenishmentSearchRequest req)
    {
        Map<String, Object> params = buildFilterParams(req);
        return snapshotMapper.search(params);
    }

    @Override
    public List<String> distinctValues(String field, String keyword)
    {
        // 映射前端字段名 → DB 列名
        String col = mapDistinctColumn(field);
        if (col == null) return Collections.emptyList();
        if (keyword != null) keyword = keyword.trim();
        return snapshotMapper.selectDistinctValues(col, keyword);
    }

    // ========================================================================
    // 快照刷新：批量写入
    // ========================================================================

    @Override
    @Transactional
    public int refreshSnapshot()
    {
        log.info("==== eBay补货快照刷新 开始 ====");
        long start = System.currentTimeMillis();

        List<EbayReplenishmentSnapshot> computed = computeService.compute();

        // 事务内：清空 → 批量插入
        if (computed.isEmpty())
        {
            log.warn("==== eBay replenishment snapshot refresh returned empty result, keep current snapshot ====");
            return 0;
        }

        String batchNo = newBatchNo("EBAY_REPL");
        if (!computed.isEmpty())
        {
            // 分批插入，每批 500 条
            int batchSize = 500;
            for (int i = 0; i < computed.size(); i += batchSize)
            {
                int end = Math.min(i + batchSize, computed.size());
                snapshotMapper.batchInsertSnapshots(computed.subList(i, end), batchNo);
            }
        }
        snapshotMapper.activateBatch(batchNo);
        snapshotMapper.deleteNonCurrent();

        log.info("==== eBay补货快照刷新 完成: {} 条 耗时{}ms ====", computed.size(), System.currentTimeMillis() - start);
        return computed.size();
    }

    private String newBatchNo(String prefix)
    {
        return prefix + "-" + System.currentTimeMillis();
    }

    // ========================================================================
    // 筛选参数构建
    // ========================================================================

    private Map<String, Object> buildFilterParams(EbayReplenishmentSearchRequest req)
    {
        Map<String, Object> p = new HashMap<>();

        // 排序
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

            // 文本字段
            if (TEXT_FIELDS.contains(field))
            {
                if (!StringUtils.hasText(f.getValue())) continue;
                p.put(field, f.getValue().trim());
                continue;
            }

            // 数值字段
            if (NUMERIC_FIELD_MAP.containsKey(field))
            {
                parseNumericFilter(p, field, f);
            }
        }

        return p;
    }

    /**
     * 解析数值筛选。支持两种格式：
     * 1. 新格式（结构化）：operator + value [+ value2]，优先判断
     * 2. 旧格式（兼容）：value=">30" 字符串前缀解析
     */
    private void parseNumericFilter(Map<String, Object> p, String field, EbayReplenishmentSearchRequest.FilterItem f)
    {
        String operator = f.getOperator();
        String value = f.getValue();
        String value2 = f.getValue2();

        // ---- 新格式：结构化 operator ----
        if (StringUtils.hasText(operator) && ALLOWED_OPS.contains(operator))
        {
            // isNull / isNotNull 不需要 value
            if ("isNull".equals(operator))
            {
                p.put(field + "_op", "isNull");
                return;
            }
            if ("isNotNull".equals(operator))
            {
                p.put(field + "_op", "isNotNull");
                return;
            }
            // between 需要 value + value2
            if ("between".equals(operator) && StringUtils.hasText(value) && StringUtils.hasText(value2))
            {
                try
                {
                    double v1 = Double.parseDouble(value.trim());
                    double v2 = Double.parseDouble(value2.trim());
                    if (PERCENT_FIELDS.contains(field)) { v1 /= 100.0; v2 /= 100.0; }
                    p.put(field + "_op", "between");
                    p.put(field + "_val", BigDecimal.valueOf(v1));
                    p.put(field + "_val2", BigDecimal.valueOf(v2));
                }
                catch (NumberFormatException ignored) {}
                return;
            }
            // 常规比较 (> >= < <= =) 需要 value
            if (StringUtils.hasText(value))
            {
                try
                {
                    double val = Double.parseDouble(value.trim());
                    if (PERCENT_FIELDS.contains(field)) val /= 100.0;
                    p.put(field + "_op", operator);
                    p.put(field + "_val", BigDecimal.valueOf(val));
                }
                catch (NumberFormatException ignored) {}
                return;
            }
            return;
        }

        // ---- 旧格式兼容：value=">30" 字符串前缀 ----
        if (!StringUtils.hasText(value)) return;
        String raw = value.trim();
        String op; String numStr;
        if (raw.startsWith(">="))      { op = ">="; numStr = raw.substring(2).trim(); }
        else if (raw.startsWith("<=")) { op = "<="; numStr = raw.substring(2).trim(); }
        else if (raw.startsWith(">"))  { op = ">";  numStr = raw.substring(1).trim(); }
        else if (raw.startsWith("<"))  { op = "<";  numStr = raw.substring(1).trim(); }
        else if (raw.startsWith("="))  { op = "=";  numStr = raw.substring(1).trim(); }
        else { op = "="; numStr = raw; }

        if (numStr.isEmpty()) return;

        try
        {
            double val = Double.parseDouble(numStr);
            if (PERCENT_FIELDS.contains(field)) val /= 100.0;
            p.put(field + "_op", op);
            p.put(field + "_val", BigDecimal.valueOf(val));
        }
        catch (NumberFormatException e)
        {
            p.put(field, raw);
        }
    }

    // ========================================================================
    // 工具
    // ========================================================================

    private void normalizeSort(EbayReplenishmentSnapshot s)
    {
        if (s.getSortField() == null || !SORT_FIELDS.contains(s.getSortField()))
        {
            s.setSortField(null);
            s.setSortOrder(null);
        }
        else if (!"ascending".equals(s.getSortOrder()))
        {
            s.setSortOrder("descending");
        }
    }

    private String mapDistinctColumn(String field)
    {
        if (field == null) return null;
        if (DISTINCT_FIELDS.contains(field)) return field;
        // 尝试映射数值字段的前端名 → DB 列名
        return NUMERIC_FIELD_MAP.get(field);
    }

    @Override
    public void updateProductNature(Long id, Integer productNature) {
        snapshotMapper.updateProductNature(id, productNature);
    }
}
