package com.ruoyi.system.service.operation.impl;

import java.math.BigDecimal;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import com.ruoyi.system.domain.operation.EbayPriceTrackingSnapshot;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.external.EbayLinkTemplate;
import com.ruoyi.system.domain.operation.external.GoodcangProductInfo;
import com.ruoyi.system.mapper.operation.EbayPriceTrackingSnapshotMapper;
import com.ruoyi.system.mapper.operation.external.EbayLinkTemplateMapper;
import com.ruoyi.system.mapper.operation.external.EbayProductDedupMapper;
import com.ruoyi.system.mapper.operation.external.GoodcangProductInfoMapper;
import com.ruoyi.system.service.operation.IEbayPriceTrackingService;
import com.ruoyi.system.service.operation.compute.EbayPriceTrackingComputeService;
import com.ruoyi.system.service.operation.compute.InventoryUtils;
import com.ruoyi.system.service.operation.compute.TrackingProfitCalcService;

@Service
public class EbayPriceTrackingServiceImpl implements IEbayPriceTrackingService
{
    private static final Logger log = LoggerFactory.getLogger(EbayPriceTrackingServiceImpl.class);

    private static final Set<String> SORT_FIELDS = Set.of(
        "site", "sku", "sales3d", "sales7d", "sales30d", "sales90d", "maxMonthlySales",
        "overseasStock", "overseasStockAgeDays", "stockSalesRatio", "estimatedReplenishQty",
        "ourLowestPrice", "trackingPrice", "trackingProfitMargin", "floorPrice", "returnRate"
    );
    private static final Set<String> TEXT_FIELDS = Set.of("site", "sku", "productName", "brandCode", "operatorName", "skuLevel");
    private static final Map<String, String> NUM_MAP = new LinkedHashMap<>();
    static {
        NUM_MAP.put("ourLowestPrice", "our_lowest_price");
        NUM_MAP.put("trackingPrice", "tracking_price");
        NUM_MAP.put("trackingProfitMargin", "tracking_profit_margin");
        NUM_MAP.put("floorPrice", "floor_price");
        NUM_MAP.put("returnRate", "return_rate");
        NUM_MAP.put("sales3d", "sales_3d");
        NUM_MAP.put("sales7d", "sales_7d");
        NUM_MAP.put("sales30d", "sales_30d");
        NUM_MAP.put("sales90d", "sales_90d");
        NUM_MAP.put("maxMonthlySales", "max_monthly_sales");
        NUM_MAP.put("overseasStock", "overseas_stock");
        NUM_MAP.put("overseasStockAgeDays", "overseas_stock_age_days");
        NUM_MAP.put("stockSalesRatio", "stock_sales_ratio");
        NUM_MAP.put("estimatedReplenishQty", "estimated_replenish_qty");
    }
    private static final Set<String> ALLOWED_OPS = Set.of("=", ">", ">=", "<", "<=", "between", "isNull", "isNotNull");
    private static final Set<String> PERCENT_FIELDS = Set.of("trackingProfitMargin", "returnRate", "stockSalesRatio");
    private static final Set<String> DISTINCT_COLS = Set.of("site", "sku_level", "brand_code", "operator_name", "product_name", "sku");

    @Autowired private EbayPriceTrackingSnapshotMapper mapper;
    @Autowired private EbayPriceTrackingComputeService computeService;
    @Autowired private TrackingProfitCalcService profitCalcService;
    @Autowired private EbayProductDedupMapper dedupMapper;
    @Autowired private EbayLinkTemplateMapper linkTemplateMapper;
    @Autowired private GoodcangProductInfoMapper productInfoMapper;

    // ========== 查询 ==========
    @Override
    public List<EbayPriceTrackingSnapshot> search(EbayReplenishmentSearchRequest req)
    {
        return mapper.search(buildParams(req));
    }

    @Override
    public List<String> distinctValues(String field, String keyword)
    {
        if (field == null || !DISTINCT_COLS.contains(field)) return Collections.emptyList();
        return mapper.selectDistinctValues(field, keyword != null ? keyword.trim() : null);
    }

    // ========== 刷新 ==========
    @Override
    @Transactional
    public int refreshSnapshot()
    {
        log.info("==== eBay每日跟价快照刷新 开始 ====");
        long t = System.currentTimeMillis();
        List<EbayPriceTrackingSnapshot> computed = computeService.compute();
        if (computed.isEmpty())
        {
            log.warn("==== eBay price tracking snapshot refresh returned empty result, keep current snapshot ====");
            return 0;
        }

        String batchNo = newBatchNo("EBAY_PRICE");
        if (!computed.isEmpty())
        {
            int batch = 500;
            for (int i = 0; i < computed.size(); i += batch)
                mapper.batchInsert(computed.subList(i, Math.min(i + batch, computed.size())), batchNo);
        }
        mapper.activateBatch(batchNo);
        int filled = mapper.fillReplenishQtyFromSnapshot();
        log.info("==== eBay每日跟价快照刷新 完成: {}条, 补货数量填充{}条, 耗时{}ms ====", computed.size(), filled, System.currentTimeMillis() - t);
        return computed.size();
    }

    private String newBatchNo(String prefix)
    {
        return prefix + "-" + System.currentTimeMillis();
    }

    // ========== 跟卖价格计算 ==========
    @Override
    public Map<String, Object> calcTracking(String site, String sku, String trackingPrice)
    {
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("success", true);

        BigDecimal M = null;
        if (StringUtils.hasText(trackingPrice))
        {
            try
            {
                M = new BigDecimal(trackingPrice.trim());
            }
            catch (Exception e)
            {
                resp.put("success", false);
                resp.put("message", "跟卖价格格式不正确");
                resp.put("trackingPrice", trackingPrice);
                resp.put("trackingProfitMargin", null);
                resp.put("floorPrice", null);
                return resp;
            }
        }
        if (M == null || M.compareTo(BigDecimal.ZERO) <= 0)
        {
            resp.put("trackingPrice", null);
            resp.put("trackingProfitMargin", null);
            resp.put("floorPrice", null);
            saveTrackingCalcDedup(site, sku, null, null, null);
            return resp;
        }
        resp.put("trackingPrice", M);

        String mid = InventoryUtils.extractMiddleCodeForInventory(sku);
        if (mid.isEmpty() && sku != null && !sku.isEmpty()) mid = sku;
        GoodcangProductInfo gp = productInfoMapper.selectByMiddleCode(mid);
        if (gp == null && mid.contains("-"))
        {
            String pureMiddleCode = mid.substring(mid.lastIndexOf('-') + 1);
            gp = productInfoMapper.selectByMiddleCode(pureMiddleCode);
            if (gp != null) mid = pureMiddleCode;
        }
        // 跨品牌数字键 fallback: VLV-170084 → numericKey=170084 → JMH-170084
        if (gp == null)
        {
            String numKey = InventoryUtils.extractNumericKey(sku);
            if (!numKey.isEmpty())
            {
                for (GoodcangProductInfo p : productInfoMapper.selectAll())
                {
                    if (p.getSkuMiddle() != null && numKey.equals(InventoryUtils.extractNumericKey(p.getSkuMiddle())))
                    {
                        gp = p; mid = p.getSkuMiddle(); break;
                    }
                }
            }
        }
        if (gp == null || gp.getPrice() == null)
        {
            resp.put("message", "未找到谷仓商品单价，SKU中间码：" + mid);
            resp.put("trackingProfitMargin", null);
            resp.put("floorPrice", null);
            saveTrackingCalcDedup(site, sku, M, null, null);
            return resp;
        }

        EbayLinkTemplate lt = linkTemplateMapper.selectBySite(site);
        if (lt == null || lt.getExchangeRate() == null || lt.getExchangeRate().compareTo(BigDecimal.ZERO) == 0)
        {
            resp.put("message", "未配置站点汇率：" + site);
            resp.put("trackingProfitMargin", null);
            resp.put("floorPrice", null);
            saveTrackingCalcDedup(site, sku, M, null, null);
            return resp;
        }

        TrackingProfitCalcService.CalcResult cr = profitCalcService.calc(site, M, gp, lt);
        resp.put("trackingProfitMargin", cr.trackingProfitMargin);
        resp.put("floorPrice", cr.floorPrice);
        saveTrackingCalcDedup(site, sku, M, cr.trackingProfitMargin, cr.floorPrice);

        return resp;
    }

    // ========== 保存操作（写 ebay_product_dedup） ==========

    @Override
    public void saveTrackingPrice(String site, String sku, String trackingPrice)
    {
        BigDecimal price = (trackingPrice != null && !trackingPrice.isEmpty())
                ? new BigDecimal(trackingPrice) : null;
        saveTrackingCalcDedup(site, sku, price, null, null);
    }

    @Override
    public Map<String, Object> saveOeNumber(String site, String sku, String oeNumber)
    {
        ensureDedupUpdated(dedupMapper.updateOeNumber(site, sku, oeNumber), site, sku);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("oeNumber", oeNumber);
        EbayLinkTemplate lt = linkTemplateMapper.selectBySite(site);
        if (lt != null) {
            result.put("presaleUrl", (lt.getPresaleUrl() != null ? lt.getPresaleUrl() : "").replace("{oe}", oeNumber != null ? oeNumber : ""));
            result.put("soldUrl", (lt.getSoldUrl() != null ? lt.getSoldUrl() : "").replace("{oe}", oeNumber != null ? oeNumber : ""));
        }
        return result;
    }

    @Override
    public void saveRemark(String site, String sku, String remark)
    {
        ensureDedupUpdated(dedupMapper.updateRemark(site, sku, remark), site, sku);
    }

    private void saveTrackingCalcDedup(String site, String sku,
            BigDecimal trackingPrice, BigDecimal margin, BigDecimal floor)
    {
        ensureDedupUpdated(dedupMapper.updateTrackingCalc(site, sku, trackingPrice, margin, floor), site, sku);
    }

    private void ensureDedupUpdated(int rows, String site, String sku)
    {
        if (rows == 0)
            throw new RuntimeException("未找到 eBay 商品记录，无法保存：" + site + " / " + sku);
    }

    // ========== 链接模板 ==========
    @Override
    public List<EbayLinkTemplate> listLinkTemplates() { return linkTemplateMapper.selectAll(); }

    @Override
    public void saveLinkTemplate(EbayLinkTemplate template) { linkTemplateMapper.upsert(template); }

    @Override
    public void deleteLinkTemplate(String site) { linkTemplateMapper.deleteBySite(site); }

    // ========== 导出 ==========
    @Override
    public List<EbayPriceTrackingSnapshot> listAll(EbayPriceTrackingSnapshot filter)
    {
        EbayReplenishmentSearchRequest req = new EbayReplenishmentSearchRequest();
        if (filter.getFilters() != null) req.setFilters(filter.getFilters());
        req.setSortField(filter.getSortField());
        req.setSortOrder(filter.getSortOrder());
        return mapper.search(buildParams(req));
    }

    // ========== 查询参数 ==========
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
        // mapper XML 用 DB 列名做参数键（如 sales_30d_op），不是前端字段名（如 sales30d_op）
        String db = NUM_MAP.getOrDefault(field, field);

        // 新格式：结构化 operator
        if (StringUtils.hasText(operator) && ALLOWED_OPS.contains(operator))
        {
            if ("isNull".equals(operator)) { p.put(db + "_op", "isNull"); return; }
            if ("isNotNull".equals(operator)) { p.put(db + "_op", "isNotNull"); return; }
            if ("between".equals(operator) && StringUtils.hasText(value) && StringUtils.hasText(value2))
            {
                try {
                    double v1 = Double.parseDouble(value.trim());
                    double v2 = Double.parseDouble(value2.trim());
                    if (PERCENT_FIELDS.contains(field)) { v1 /= 100.0; v2 /= 100.0; }
                    p.put(db + "_op", "between");
                    p.put(db + "_val", BigDecimal.valueOf(v1));
                    p.put(db + "_val2", BigDecimal.valueOf(v2));
                } catch (NumberFormatException ignored) {}
                return;
            }
            if (StringUtils.hasText(value))
            {
                try {
                    double v = Double.parseDouble(value.trim());
                    if (PERCENT_FIELDS.contains(field)) v /= 100.0;
                    p.put(db + "_op", operator);
                    p.put(db + "_val", BigDecimal.valueOf(v));
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
        try
        {
            double v = Double.parseDouble(ns);
            if (PERCENT_FIELDS.contains(field)) v /= 100.0;
            p.put(db + "_op", op);
            p.put(db + "_val", BigDecimal.valueOf(v));
        }
        catch (NumberFormatException e) { p.put(field, raw); }
    }
}
