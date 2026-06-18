package com.ruoyi.system.service.operation.impl;

import java.math.BigDecimal;
import java.util.*;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import com.ruoyi.system.domain.operation.EbayPriceTrackingSnapshot;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.external.EbayLinkTemplate;
import com.ruoyi.system.domain.operation.external.EbayProductDedup;
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
    private static final Set<String> TEXT_FIELDS = Set.of("site", "sku", "productName", "brandCode", "operatorName");
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
    private static final Set<String> PERCENT_FIELDS = Set.of("trackingProfitMargin", "returnRate", "stockSalesRatio");
    private static final Set<String> DISTINCT_COLS = Set.of("site", "sku_level", "brand_code", "operator_name", "product_name", "sku");

    @Autowired private EbayPriceTrackingSnapshotMapper mapper;
    @Autowired private EbayPriceTrackingComputeService computeService;
    @Autowired private TrackingProfitCalcService profitCalcService;
    @Autowired private EbayProductDedupMapper dedupMapper;
    @Autowired private EbayLinkTemplateMapper linkTemplateMapper;
    @Autowired private GoodcangProductInfoMapper productInfoMapper;

    // ========== 搜索 ==========
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
    public void refreshSnapshot()
    {
        log.info("==== eBay每日跟价快照刷新 开始 ====");
        long t = System.currentTimeMillis();
        List<EbayPriceTrackingSnapshot> computed = computeService.compute();
        mapper.deleteAll();
        if (!computed.isEmpty())
        {
            int batch = 500;
            for (int i = 0; i < computed.size(); i += batch)
                mapper.batchInsert(computed.subList(i, Math.min(i + batch, computed.size())));
        }
        log.info("==== eBay每日跟价快照刷新 完成: {} 条 耗时{}ms ====", computed.size(), System.currentTimeMillis() - t);
    }

    // ========== 跟卖计算 ==========
    @Override
    public Map<String, Object> calcTracking(String site, String sku, String trackingPrice)
    {
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("success", true);

        BigDecimal M = null;
        if (trackingPrice != null && !trackingPrice.isEmpty())
        {
            try { M = new BigDecimal(trackingPrice); } catch (Exception e) {}
        }
        if (M == null || M.compareTo(BigDecimal.ZERO) <= 0)
        {
            resp.put("trackingProfitMargin", null);
            resp.put("floorPrice", null);
            return resp;
        }

        String mid = InventoryUtils.extractMiddleCodeForInventory(sku);
        if (mid.isEmpty() && sku != null && !sku.isEmpty()) mid = sku;
        GoodcangProductInfo gp = productInfoMapper.selectByMiddleCode(mid);
        if (gp == null || gp.getPrice() == null)
        {
            resp.put("trackingProfitMargin", null);
            resp.put("floorPrice", null);
            return resp;
        }

        EbayLinkTemplate lt = linkTemplateMapper.selectBySite(site);
        if (lt == null || lt.getExchangeRate() == null || lt.getExchangeRate().compareTo(BigDecimal.ZERO) == 0)
        {
            resp.put("trackingProfitMargin", null);
            resp.put("floorPrice", null);
            return resp;
        }

        TrackingProfitCalcService.CalcResult cr = profitCalcService.calc(site, M, gp, lt);
        resp.put("trackingProfitMargin", cr.trackingProfitMargin);
        resp.put("floorPrice", cr.floorPrice);

        // 保存到 ebay_product_dedup
        saveTrackingCalcToDedup(site, sku, M, cr.trackingProfitMargin, cr.floorPrice);

        return resp;
    }

    private void saveTrackingCalcToDedup(String site, String sku, BigDecimal price, BigDecimal margin, BigDecimal floor)
    {
        List<EbayProductDedup> all = dedupMapper.selectAll();
        for (EbayProductDedup d : all)
        {
            if (site.equals(d.getSite()) && sku.equals(d.getSku()))
            {
                if (price != null) d.setTrackingPrice(price);
                if (margin != null) d.setTrackingProfitMargin(margin);
                if (floor != null) d.setFloorPrice(floor);
                return;
            }
        }
    }

    // ========== 保存操作 ==========
    @Override
    public void saveTrackingPrice(String site, String sku, String trackingPrice)
    {
        saveTrackingCalcToDedup(site, sku, trackingPrice != null && !trackingPrice.isEmpty() ? new BigDecimal(trackingPrice) : null, null, null);
    }

    @Override
    public void saveOeNumber(String site, String sku, String oeNumber)
    {
        for (EbayProductDedup d : dedupMapper.selectAll())
            if (site.equals(d.getSite()) && sku.equals(d.getSku())) { d.setOeNumber(oeNumber); return; }
    }

    @Override
    public void saveRemark(String site, String sku, String remark)
    {
        for (EbayProductDedup d : dedupMapper.selectAll())
            if (site.equals(d.getSite()) && sku.equals(d.getSku())) { d.setRemark(remark); return; }
    }

    // ========== 链接模板 ==========
    @Override
    public List<EbayLinkTemplate> listLinkTemplates() { return linkTemplateMapper.selectAll(); }

    @Override
    public void saveLinkTemplate(EbayLinkTemplate template) { linkTemplateMapper.upsert(template); }

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

    // ========== 参数构建 ==========
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
        try
        {
            double v = Double.parseDouble(ns);
            if (PERCENT_FIELDS.contains(field)) v /= 100.0;
            p.put(field + "_op", op);
            p.put(field + "_val", BigDecimal.valueOf(v));
        }
        catch (NumberFormatException e) { p.put(field, raw); }
    }
}
