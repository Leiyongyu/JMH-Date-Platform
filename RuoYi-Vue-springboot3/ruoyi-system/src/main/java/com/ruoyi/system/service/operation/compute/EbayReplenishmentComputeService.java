package com.ruoyi.system.service.operation.compute;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;
import com.ruoyi.system.domain.operation.external.*;
import com.ruoyi.system.mapper.operation.external.*;
import com.ruoyi.system.service.operation.external.lingxing.LingxingProperties;

/**
 * eBay补货计算引擎 —— 从旧项目 InventoryOverviewServiceImpl.computeOverview() + InventoryComputeEngine 移植。
 *
 * 核心流程：
 *   1. ebay_product_dedup → 按 site + groupKey(去PC) 归并基础行
 *   2. warehouse_inventory_detail → 按仓库类型汇总库存（海外/成都、可售/在途/锁定）
 *   3. ebay_sales → 按 site + middleCode 聚合 7/30/90天 & 自然月最大销量
 *   4. goodcang GRN → 计算最近出库时间 & 出库天数
 *   5. purchase_order + warehouse_statement(type=22) → 采购周期、待交付数
 *   6. purchase_plan(待审批) → 采购计划数
 *   7. brand_owner → 匹配负责人
 *   8. 汇总写入 ebay_replenishment_snapshot
 */
@Service
public class EbayReplenishmentComputeService
{
    private static final Logger log = LoggerFactory.getLogger(EbayReplenishmentComputeService.class);

    private final LingxingProperties lingxingProperties;
    private final WarehouseMapper warehouseMapper;
    private final WarehouseInventoryDetailMapper inventoryMapper;
    private final EbayProductDedupMapper dedupMapper;
    private final EbaySalesMapper ebaySalesMapper;
    private final GoodcangGrnListMapper grnListMapper;
    private final GoodcangGrnDetailMapper grnDetailMapper;
    private final GoodcangWarehouseMapper gcWarehouseMapper;
    private final PurchaseOrderMapper purchaseOrderMapper;
    private final PurchasePlanMapper purchasePlanMapper;
    private final WarehouseStatementMapper warehouseStatementMapper;
    private final BrandOwnerMapper brandOwnerMapper;
    private final com.ruoyi.system.mapper.operation.external.EbayReplenishFormulaMapper formulaMapper;

    public EbayReplenishmentComputeService(
            LingxingProperties lingxingProperties,
            WarehouseMapper warehouseMapper,
            WarehouseInventoryDetailMapper inventoryMapper,
            EbayProductDedupMapper dedupMapper,
            EbaySalesMapper ebaySalesMapper,
            GoodcangGrnListMapper grnListMapper,
            GoodcangGrnDetailMapper grnDetailMapper,
            GoodcangWarehouseMapper gcWarehouseMapper,
            PurchaseOrderMapper purchaseOrderMapper,
            PurchasePlanMapper purchasePlanMapper,
            WarehouseStatementMapper warehouseStatementMapper,
            BrandOwnerMapper brandOwnerMapper,
            com.ruoyi.system.mapper.operation.external.EbayReplenishFormulaMapper formulaMapper)
    {
        this.lingxingProperties = lingxingProperties;
        this.warehouseMapper = warehouseMapper;
        this.inventoryMapper = inventoryMapper;
        this.dedupMapper = dedupMapper;
        this.ebaySalesMapper = ebaySalesMapper;
        this.grnListMapper = grnListMapper;
        this.grnDetailMapper = grnDetailMapper;
        this.gcWarehouseMapper = gcWarehouseMapper;
        this.purchaseOrderMapper = purchaseOrderMapper;
        this.purchasePlanMapper = purchasePlanMapper;
        this.warehouseStatementMapper = warehouseStatementMapper;
        this.brandOwnerMapper = brandOwnerMapper;
        this.formulaMapper = formulaMapper;
    }

    // ========================================================================
    // 公开入口
    // ========================================================================

    /**
     * 执行全量计算，返回快照行列表。
     * 调用方负责写入 ebay_replenishment_snapshot。
     */
    public List<EbayReplenishmentSnapshot> compute()
    {
        log.info("==== eBay补货重算 开始 ====");
        long start = System.currentTimeMillis();

        // ---- 0. 仓库映射 ----
        List<Integer> inventoryWids = parseInventoryWids();
        Map<Integer, Warehouse> warehouseByWid = loadWarehouseMap(inventoryWids);
        Map<Integer, String> widToSite = buildWidToSite(warehouseByWid);

        // ---- 1. 基准行 (groupKey → site → 元信息) ----
        Map<String, Map<String, SkuSiteRow>> siteRowsBySku = new LinkedHashMap<>();
        Map<String, String> skuProductNameMap = new LinkedHashMap<>();
        Map<String, BigDecimal> profitRateMap = new LinkedHashMap<>();  // key = site|middleCode
        Map<String, BigDecimal> returnRateMap = new LinkedHashMap<>();  // key = site|middleCode
        // 老品判断集合：dedup 中有则老品
        Set<String> oldSkuSet = new HashSet<>();

        for (EbayProductDedup dedup : dedupMapper.selectAll())
        {
            String rawSku = dedup.getSku();
            if (rawSku == null || (rawSku = rawSku.trim()).isEmpty()) continue;
            String groupKey = InventoryUtils.extractInventoryGroupKey(rawSku);
            if (groupKey.isEmpty()) continue;
            String site = InventoryUtils.normalizeSite(dedup.getSite());
            if (site == null || site.isEmpty()) continue;

            if (!skuProductNameMap.containsKey(groupKey) && dedup.getProductName() != null)
                skuProductNameMap.put(groupKey, dedup.getProductName().trim());

            siteRowsBySku.computeIfAbsent(groupKey, k -> new LinkedHashMap<>())
                    .put(site, new SkuSiteRow(groupKey, site));

            oldSkuSet.add(site + "|" + groupKey);

            // 利润率 & 退货率 — 用数字键匹配，跨品牌
            String numKey = InventoryUtils.extractNumericKey(rawSku);
            if (dedup.getProfitRate() != null && !numKey.isEmpty())
                profitRateMap.put(site + "|" + numKey, dedup.getProfitRate());
            if (dedup.getReturnRate() != null && !numKey.isEmpty())
                returnRateMap.put(site + "|" + numKey, dedup.getReturnRate());
        }

        // ---- 2. 库存汇总 (按 groupKey 归并 PC/非PC) ----
        // 新品判断集合：库存中但不在 dedup 中的为新品
        Set<String> inventorySkuSet = new HashSet<>();

        for (WarehouseInventoryDetail d : inventoryMapper.selectAll())
        {
            String baseSku = InventoryUtils.extractInventoryGroupKey(d.getSku());
            if (baseSku.isEmpty()) continue;
            Warehouse wh = warehouseByWid.get(parseIntOrNull(d.getWid()));
            if (wh == null) continue;
            String site = InventoryUtils.whNameToSite(wh.getName());
            if (site.isEmpty()) continue;

            String siteSkuKey = site + "|" + baseSku;
            inventorySkuSet.add(siteSkuKey);

            // 自动补入缺失行（不在 dedup 的 SKU 也能进快照）
            Map<String, SkuSiteRow> sm = siteRowsBySku.computeIfAbsent(baseSku, k -> new LinkedHashMap<>());
            SkuSiteRow row = sm.computeIfAbsent(site, s -> new SkuSiteRow(baseSku, site));

            int validNum = d.getProductValidNum();
            int onwayNum = d.getProductOnway();
            int qtyReceive = d.getQuantityReceive();
            int lockNum = d.getProductLockNum();

            row.lockNum += lockNum;
            if (wh.getType() != null && wh.getType() == 3)
            {
                // 海外仓
                row.overseasSellable += validNum;
                row.overseasOnway += onwayNum;
            }
            else
            {
                // 本地仓(成都等)：在途用 quantity_receive
                row.localSellable += validNum;
                row.localOnway += qtyReceive;
            }
        }

        // ---- 3. 谷仓出库时间 (middleCode|wid → 最新create_at) ----
        Map<String, String> outboundTimeMap = computeOutboundTimes();

        // ---- 4. 采购周期 & 待交付 & 采购计划 ----
        PurchaseAgg pa = aggregatePurchases(warehouseByWid);

        // ---- 5. eBay 销量 ----
        SalesAgg sa = aggregateSales();

        // ---- 6. 品牌负责人 ----
        Map<String, String> ownerByBrand = loadBrandOwners();

        // ---- 7. 加载公式配置 ----
        List<EbayReplenishFormula> formulas = formulaMapper.selectActive();
        log.info("eBay补货公式配置 加载 {} 条", formulas.size());

        // ---- 8. 组装结果 ----
        LocalDate today = LocalDate.now();
        List<EbayReplenishmentSnapshot> result = new ArrayList<>();
        Set<String> seen = new HashSet<>();

        for (Map.Entry<String, Map<String, SkuSiteRow>> skuEntry : siteRowsBySku.entrySet())
        {
            String baseSku = skuEntry.getKey();
            for (SkuSiteRow row : skuEntry.getValue().values())
            {
                String dedupKey = baseSku + "|" + row.site;
                if (!seen.add(dedupKey)) continue;

                EbayReplenishmentSnapshot snap = new EbayReplenishmentSnapshot();

                // ---- 基础字段 ----
                snap.setSite(row.site);
                snap.setSku(baseSku);
                snap.setProductName(skuProductNameMap.getOrDefault(baseSku, ""));

                // ---- 库存字段 ----
                snap.setOverseasOnway(row.overseasOnway);
                snap.setOverseasSellable(row.overseasSellable);
                snap.setOverseasTotal(row.overseasSellable + row.overseasOnway);
                snap.setLocalOnway(row.localOnway);
                snap.setLocalSellable(row.localSellable);
                snap.setLockedQty(row.lockNum);
                int totalInv = row.overseasSellable + row.overseasOnway + row.localSellable + row.localOnway;
                snap.setTotalInventory(totalInv);

                // ---- 销量 ----
                String salesKey = row.site + "|" + InventoryUtils.extractMiddleCodeForInventory(baseSku);
                snap.setSales7d(sa.sales7d.getOrDefault(salesKey, 0));
                snap.setSales15d(sa.sales15d.getOrDefault(salesKey, 0));
                snap.setSales30d(sa.sales30d.getOrDefault(salesKey, 0));
                snap.setSales90d(sa.sales90d.getOrDefault(salesKey, 0));
                snap.setMaxMonthlySales(sa.monthlyMax.getOrDefault(salesKey, null));

                // ---- 出库天数 ----
                String mid = InventoryUtils.extractNumericKey(baseSku);
                if (!mid.isEmpty())
                {
                    String latestTime = null;
                    for (Map.Entry<Integer, String> e : widToSite.entrySet())
                    {
                        if (row.site.equals(e.getValue()))
                        {
                            String t = outboundTimeMap.get(mid + "|" + e.getKey());
                            if (t != null && (latestTime == null || t.compareTo(latestTime) > 0))
                                latestTime = t;
                        }
                    }
                    if (latestTime != null)
                    {
                        snap.setLastLocalOutboundTime(latestTime);
                        try
                        {
                            LocalDate dt = LocalDate.parse(latestTime);
                            snap.setOutboundDays((int) ChronoUnit.DAYS.between(dt, today));
                        }
                        catch (Exception ignored) {}
                    }
                }

                // ---- 采购周期 ----
                String purchaseKey = row.site + "|" + baseSku;
                Integer cycle = pa.cycleMap.get(purchaseKey);
                if (cycle != null) snap.setPurchaseCycleDays(cycle);

                // ---- 采购待交付 & 采购计划 ----
                snap.setPurchasePendingDelivery(pa.pendingMap.getOrDefault(purchaseKey, 0));
                snap.setPurchasePlanQty(pa.planCountMap.getOrDefault(purchaseKey, 0));

                // ============================================================
                // 采购数量公式
                // ============================================================
                Integer cyc = snap.getPurchaseCycleDays();
                Integer od = snap.getOutboundDays();
                int planCount = snap.getPurchasePlanQty() != null ? snap.getPurchasePlanQty() : 0;
                boolean lowStock = snap.getPurchasePendingDelivery() <= 2
                        && snap.getLocalSellable() <= 2
                        && snap.getLocalOnway() <= 2
                        && planCount <= 2
                        && snap.getLockedQty() <= 2;
                boolean canCalc = lowStock ? (cyc != null && od != null) : (cyc != null);
                if (canCalc)
                {
                    BigDecimal avgMonthly = BigDecimal.valueOf(snap.getSales90d())
                            .divide(BigDecimal.valueOf(3), 4, RoundingMode.HALF_UP);
                    double days = lowStock ? (cyc + od) : cyc;
                    snap.setSuggestPurchaseQty(
                            avgMonthly.multiply(BigDecimal.valueOf(days / 30.0))
                                    .setScale(0, RoundingMode.HALF_UP));
                }

                // ---- 最大月销补货量 = maxMonthlySales * 4.03 - totalInventory ----
                int mm = snap.getMaxMonthlySales() != null ? snap.getMaxMonthlySales() : 0;
                snap.setMaxMonthlyReplenishQty(Math.max(0, (int) Math.round(mm * 4.03 - totalInv)));

                // ---- 月销预测 (13条公式配置化) ----
                snap.setMonthlySalesForecast(calcMonthlySalesForecast(snap, formulas));

                // ---- 库销比 ----
                int d30 = snap.getSales30d();
                snap.setOverseasSellableSalesRatio(safeDivide(snap.getOverseasSellable(), d30));
                snap.setOverseasTotalSalesRatio(safeDivide(snap.getOverseasTotal(), d30));
                snap.setTotalInventorySalesRatio(safeDivide(totalInv, d30));

                // ---- 负责人 ----
                snap.setOwnerName(InventoryUtils.matchOwner(baseSku, ownerByBrand));

                // ---- 利润率 & 退货率 ----
                if (!mid.isEmpty())
                {
                    BigDecimal pr = profitRateMap.get(row.site + "|" + mid);
                    if (pr != null) snap.setProfitRate30d(pr.multiply(BigDecimal.valueOf(100)));
                    BigDecimal rr = returnRateMap.get(row.site + "|" + mid);
                    if (rr != null) snap.setReturnRate(rr);
                }

                // ---- 产品性质（自动判定：dedup有→老品(1)，仅库存有→新品(2)） ----
                String siteSkuKey = row.site + "|" + baseSku;
                Integer productNature = oldSkuSet.contains(siteSkuKey) ? 1 :
                    (inventorySkuSet.contains(siteSkuKey) ? 2 : 1);
                snap.setProductNature(productNature);

                // ---- 月销预测 ----
                Integer forecast = calcMonthlySalesForecast(snap);
                snap.setMonthlySalesForecast(forecast);

                // ---- 月动销率 = sales30d / totalInventory * 100 ----
                if (totalInv > 0 && snap.getSales30d() != null && snap.getSales30d() > 0) {
                    snap.setMonthlyTurnoverRate(
                            BigDecimal.valueOf(snap.getSales30d())
                                    .divide(BigDecimal.valueOf(totalInv), 4, RoundingMode.HALF_UP)
                                    .multiply(BigDecimal.valueOf(100))
                                    .setScale(2, RoundingMode.HALF_UP));
                }

                // ---- 退货等级 ----
                snap.setReturnLevel(calcReturnLevel(snap.getReturnRate(), snap.getProfitRate30d(),
                        snap.getMonthlyTurnoverRate()));

                // ---- SKU 等级 ----
                snap.setSkuLevel(InventoryUtils.calcProductLevel(
                        snap.getSales30d(),
                        snap.getProfitRate30d() != null ? snap.getProfitRate30d().doubleValue() : 0));

                result.add(snap);
            }
        }

        log.info("==== eBay补货重算 完成: {} 条 耗时{}ms ====", result.size(), System.currentTimeMillis() - start);
        return result;
    }

    // ========================================================================
    // 仓库映射
    // ========================================================================

    private List<Integer> parseInventoryWids()
    {
        List<Integer> list = new ArrayList<>();
        String raw = lingxingProperties.getInventoryWids();
        if (StringUtils.hasText(raw))
        {
            for (String part : raw.split(","))
            {
                try { list.add(Integer.parseInt(part.trim())); }
                catch (NumberFormatException ignored) {}
            }
        }
        return list;
    }

    private Map<Integer, Warehouse> loadWarehouseMap(List<Integer> wids)
    {
        return warehouseMapper.selectAll().stream()
                .filter(w -> w.getWid() != null && wids.contains(w.getWid()) && w.getWid() != 1194)
                .collect(Collectors.toMap(Warehouse::getWid, w -> w, (a, b) -> a));
    }

    private Map<Integer, String> buildWidToSite(Map<Integer, Warehouse> warehouseMap)
    {
        Map<Integer, String> map = new HashMap<>();
        for (Map.Entry<Integer, Warehouse> e : warehouseMap.entrySet())
            map.put(e.getKey(), InventoryUtils.whNameToSite(e.getValue().getName()));
        return map;
    }

    // ========================================================================
    // 谷仓出库时间
    // ========================================================================

    /**
     * 返回 "middleCode|wid" → 最新出库日期 (yyyy-MM-dd)
     */
    /** 一条 SQL 聚合：mid|wid → 最新出库日期 */
    private Map<String, String> computeOutboundTimes()
    {
        Map<String, String> result = new LinkedHashMap<>();
        for (Map<String, Object> row : grnDetailMapper.selectOutboundTimes())
        {
            String mid = InventoryUtils.extractNumericKey(String.valueOf(row.get("mid")));
            Object widObj = row.get("wid");
            Object dateObj = row.get("latest_date");
            if (mid.isEmpty() || widObj == null || dateObj == null) continue;
            result.put(mid + "|" + widObj, String.valueOf(dateObj));
        }
        return result;
    }

    // ========================================================================
    // 采购聚合
    // ========================================================================

    private PurchaseAgg aggregatePurchases(Map<Integer, Warehouse> warehouseMap)
    {
        PurchaseAgg agg = new PurchaseAgg();

        // --- 采购单 ---
        for (PurchaseOrder po : purchaseOrderMapper.selectAll())
        {
            String sku = po.getItemSku();
            String whName = po.getWareHouseName();
            if (sku == null || sku.trim().isEmpty() || whName == null || whName.trim().isEmpty()) continue;
            String site = InventoryUtils.whNameToSite(whName.trim());
            if (site.isEmpty()) continue;
            String key = site + "|" + InventoryUtils.extractInventoryGroupKey(sku.trim());

            if (po.getOrderTime() != null)
            {
                LocalDate od = po.getOrderTime().toInstant().atZone(ZoneId.systemDefault()).toLocalDate();
                LocalDate ex = agg.orderTimeMap.get(key);
                if (ex == null || od.isAfter(ex)) agg.orderTimeMap.put(key, od);
            }

            String status = po.getStatusText();
            if ("待审批".equals(status) || "待下单".equals(status))
                agg.pendingMap.merge(key, 1, Integer::sum);
        }

        // --- 入库流水 (type=22) ---
        for (WarehouseStatement ws : warehouseStatementMapper.selectByType(22))
        {
            String sku = ws.getSku();
            String whName = ws.getWareHouseName();
            if (sku == null || sku.trim().isEmpty() || whName == null || whName.trim().isEmpty()
                    || ws.getOptTime() == null) continue;
            String site = InventoryUtils.whNameToSite(whName.trim());
            if (site.isEmpty()) continue;
            String key = site + "|" + InventoryUtils.extractInventoryGroupKey(sku.trim());
            LocalDate od = ws.getOptTime().toInstant().atZone(ZoneId.systemDefault()).toLocalDate();
            LocalDate ex = agg.inboundTimeMap.get(key);
            if (ex == null || od.isBefore(ex)) agg.inboundTimeMap.put(key, od);
        }

        // --- 采购周期天数 ---
        for (String k : agg.orderTimeMap.keySet())
        {
            LocalDate od = agg.orderTimeMap.get(k);
            LocalDate ib = agg.inboundTimeMap.get(k);
            if (od != null && ib != null && !ib.isBefore(od))
                agg.cycleMap.put(k, (int) ChronoUnit.DAYS.between(od, ib));
        }

        // --- 采购计划（待审批） ---
        for (PurchasePlan pp : purchasePlanMapper.selectByStatusText("待审批"))
        {
            String sku = pp.getSku();
            String whName = pp.getWarehouseName();
            if (sku == null || sku.trim().isEmpty() || whName == null || whName.trim().isEmpty()) continue;
            String site = InventoryUtils.whNameToSite(whName.trim());
            if (site.isEmpty()) continue;
            String key = site + "|" + InventoryUtils.extractInventoryGroupKey(sku.trim());
            agg.planCountMap.merge(key, 1, Integer::sum);
        }

        return agg;
    }

    private static class PurchaseAgg
    {
        final Map<String, LocalDate> orderTimeMap = new LinkedHashMap<>();
        final Map<String, LocalDate> inboundTimeMap = new LinkedHashMap<>();
        final Map<String, Integer> pendingMap = new LinkedHashMap<>();
        final Map<String, Integer> cycleMap = new LinkedHashMap<>();
        final Map<String, Integer> planCountMap = new LinkedHashMap<>();
    }

    // ========================================================================
    // 销量聚合
    // ========================================================================

    private SalesAgg aggregateSales()
    {
        SalesAgg agg = new SalesAgg();
        LocalDate today = LocalDate.now();
        LocalDate cutoff7d = today.minusDays(7);
        LocalDate cutoff15d = today.minusDays(15);
        LocalDate cutoff30d = today.minusDays(30);
        LocalDate cutoff90d = today.minusDays(90);

        for (EbaySales s : ebaySalesMapper.selectAll())
        {
            String rawSku = s.getSku();
            String currency = s.getCurrency();
            if (rawSku == null || rawSku.isEmpty() || currency == null || currency.isEmpty()) continue;
            String mid = InventoryUtils.extractMiddleCodeForInventory(rawSku);
            if (mid.isEmpty()) continue;
            String site = InventoryUtils.currencyToSite(currency.toUpperCase());
            if (site.isEmpty()) continue;

            LocalDate pd = s.getPaymentTime() != null
                    ? s.getPaymentTime().toInstant().atZone(ZoneId.systemDefault()).toLocalDate()
                    : null;
            if (pd == null) continue;

            int qty = s.getQuantity() != null ? s.getQuantity() : 0;
            String key = site + "|" + mid;

            if (!pd.isBefore(cutoff7d)) agg.sales7d.merge(key, qty, Integer::sum);
            if (!pd.isBefore(cutoff15d)) agg.sales15d.merge(key, qty, Integer::sum);
            if (!pd.isBefore(cutoff30d)) agg.sales30d.merge(key, qty, Integer::sum);
            if (!pd.isBefore(cutoff90d)) agg.sales90d.merge(key, qty, Integer::sum);

            // 按自然月聚合
            String monthKey = pd.getYear() + "-" + String.format("%02d", pd.getMonthValue());
            agg.monthlySales.computeIfAbsent(key, k -> new LinkedHashMap<>())
                    .merge(monthKey, qty, Integer::sum);
        }

        // 每个key取最大月销量
        for (Map.Entry<String, Map<String, Integer>> e : agg.monthlySales.entrySet())
        {
            int max = e.getValue().values().stream().max(Integer::compareTo).orElse(0);
            agg.monthlyMax.put(e.getKey(), max);
        }

        return agg;
    }

    private static class SalesAgg
    {
        final Map<String, Integer> sales7d = new LinkedHashMap<>();
        final Map<String, Integer> sales15d = new LinkedHashMap<>();
        final Map<String, Integer> sales30d = new LinkedHashMap<>();
        final Map<String, Integer> sales90d = new LinkedHashMap<>();
        final Map<String, Map<String, Integer>> monthlySales = new LinkedHashMap<>();
        final Map<String, Integer> monthlyMax = new LinkedHashMap<>();
    }

    // ========================================================================
    // 品牌负责人
    // ========================================================================

    private Map<String, String> loadBrandOwners()
    {
        return brandOwnerMapper.selectAll().stream()
                .collect(Collectors.toMap(
                        b -> StringUtils.hasText(b.getBrandCode()) ? b.getBrandCode().trim().toUpperCase() : "",
                        b -> StringUtils.hasText(b.getOwnerName()) ? b.getOwnerName().trim() : "",
                        (a, b) -> a));
    }

    // ========================================================================
    // 工具
    // ========================================================================

    private static Integer parseIntOrNull(String s)
    {
        if (s == null || s.isEmpty()) return null;
        try { return Integer.parseInt(s); }
        catch (NumberFormatException e) { return null; }
    }

    /** 月销预测公式：按产品性质和老品13场景 */
    private Integer calcMonthlySalesForecast(EbayReplenishmentSnapshot snap) {
        int d7 = snap.getSales7d() != null ? snap.getSales7d() : 0;
        int d15 = snap.getSales15d() != null ? snap.getSales15d() : 0;
        int d30 = snap.getSales30d() != null ? snap.getSales30d() : 0;
        int age = snap.getOutboundDays() != null ? snap.getOutboundDays() : 0;
        Integer pn = snap.getProductNature();

        // 新品：30天销量 × 30 / 出库天数
        if (pn != null && pn == 2) {
            if (age > 0 && d30 > 0)
                return Math.max(0, (int) Math.round((double) d30 * 30 / age));
            return d30; // 出库天数为空，降级为老品场景12
        }

        // 老品：13场景
        double r7 = d7 > 0 ? (double) d7 / 7 : 0;
        double r15 = d15 > 0 ? (double) d15 / 15 : 0;
        double r30 = d30 > 0 ? (double) d30 / 30 : 0;

        if (d7 > 0) {
            if (r7 >= d30 * 1.2 / 30)
                return (int) Math.round((r7 * 0.7  + r15 * 0.2  + r30 * 0.1 ) * 30);
            if (r7 >= d30 * 1.0 / 30)
                return (int) Math.round((r7 * 0.6  + r15 * 0.25 + r30 * 0.15) * 30);
            if (r7 >= d30 * 0.8 / 30)
                return (int) Math.round((r7 * 0.5  + r15 * 0.3  + r30 * 0.2 ) * 30);
            if (r7 >= d30 * 0.5 / 30)
                return (int) Math.round((r7 * 0.35 + r15 * 0.35 + r30 * 0.3 ) * 30);
            return (int) Math.round((r7 * 0.2  + r15 * 0.3  + r30 * 0.5 ) * 30);
        }
        if (d15 > 0) {
            if (r15 >= d30 * 1.3 / 30)
                return (int) Math.round((r15 * 0.6 + r30 * 0.4) * 30);
            if (r15 >= d30 * 1.1 / 30)
                return (int) Math.round((r15 * 0.5 + r30 * 0.5) * 30);
            if (r15 >= d30 * 0.9 / 30)
                return (int) Math.round((r15 * 0.4 + r30 * 0.6) * 30);
            if (r15 >= d30 * 0.6 / 30)
                return (int) Math.round((r15 * 0.3 + r30 * 0.7) * 30);
            return (int) Math.round((r15 * 0.2 + r30 * 0.8) * 30);
        }
        return d30; // 场景11/12
    }

    private static BigDecimal safeDivide(int a, int b)
    {
        return InventoryUtils.safeDivide(a, b);
    }

    // ========================================================================
    // 月销预测公式 (配置化, 13条规则)
    // ========================================================================

    private static int calcMonthlySalesForecast(EbayReplenishmentSnapshot snap, List<EbayReplenishFormula> formulas)
    {
        int d7 = nvl(snap.getSales7d());
        int d15 = nvl(snap.getSales15d());
        int d30 = nvl(snap.getSales30d());
        int age = nvl(snap.getOutboundDays());

        // 产品性质: null 视为 1 (老品)
        int nature = snap.getProductNature() != null ? snap.getProductNature() : 1;

        // ---- 新品规则: result = d30 * 30 / age ----
        if (nature == 0)
        {
            if (d30 > 0 && age > 0)
            {
                return (int) Math.max(0, Math.round((double) d30 * 30.0 / age));
            }
            return 0;
        }

        // ---- 老品规则 ----
        double d7Avg = d7 > 0 ? (double) d7 / 7.0 : 0;
        double d15Avg = d15 > 0 ? (double) d15 / 15.0 : 0;
        double d30Avg = d30 > 0 ? (double) d30 / 30.0 : 0;

        // 优先级: OLD_D7_POSITIVE → OLD_D7_ZERO_D15_POSITIVE → OLD_NO_SALES
        List<EbayReplenishFormula> d7Rules = new ArrayList<>();
        List<EbayReplenishFormula> d15Rules = new ArrayList<>();
        List<EbayReplenishFormula> noSalesRules = new ArrayList<>();

        for (EbayReplenishFormula f : formulas)
        {
            String g = f.getRuleGroup();
            if (g == null) continue;
            if (g.contains("D7_POSITIVE")) d7Rules.add(f);
            else if (g.contains("D15_POSITIVE")) d15Rules.add(f);
            else if (g.contains("NO_SALES")) noSalesRules.add(f);
        }

        // 按 scenario_order 排序
        d7Rules.sort((a, b) -> Integer.compare(a.getScenarioOrder(), b.getScenarioOrder()));
        d15Rules.sort((a, b) -> Integer.compare(a.getScenarioOrder(), b.getScenarioOrder()));
        noSalesRules.sort((a, b) -> Integer.compare(a.getScenarioOrder(), b.getScenarioOrder()));

        EbayReplenishFormula matched = null;

        if (d7 > 0)
        {
            matched = matchRule(d7Avg, d30Avg, d7Rules);
        }
        else if (d15 > 0)
        {
            matched = matchRule(d15Avg, d30Avg, d15Rules);
        }

        if (matched != null)
        {
            return applyWeightedFormula(d7, d15, d30, matched);
        }

        // fallback: noSalesRules 的最后一条(规则12/13)
        if (d30 > 0 && !noSalesRules.isEmpty())
        {
            EbayReplenishFormula f = noSalesRules.get(0); // d30>0 规则
            return applyWeightedFormula(d7, d15, d30, f);
        }

        return 0;
    }

    private static EbayReplenishFormula matchRule(double metricAvg, double d30Avg, List<EbayReplenishFormula> rules)
    {
        for (EbayReplenishFormula f : rules)
        {
            if (f.getCompareMetric() == null || "NONE".equals(f.getCompareMetric())) continue;
            BigDecimal lb = f.getLowerBound();
            BigDecimal ub = f.getUpperBound();

            double thresholdLower = lb != null ? d30Avg * lb.doubleValue() : 0;
            double thresholdUpper = ub != null ? d30Avg * ub.doubleValue() : -1;

            if (lb != null && ub != null)
            {
                // 区间匹配: lowerBound <= metricAvg/d30Avg < upperBound
                if (metricAvg >= thresholdLower && metricAvg < thresholdUpper) return f;
            }
            else if (lb != null)
            {
                // 仅下限: metricAvg >= d30Avg * lowerBound
                if (metricAvg >= thresholdLower) return f;
            }
            else if (ub != null)
            {
                // 仅上限: metricAvg < d30Avg * upperBound
                if (metricAvg < thresholdUpper) return f;
            }
        }
        return null;
    }

    private static int applyWeightedFormula(int d7, int d15, int d30, EbayReplenishFormula f)
    {
        double w7 = f.getWeight7d() != null ? f.getWeight7d().doubleValue() : 0;
        double w15 = f.getWeight15d() != null ? f.getWeight15d().doubleValue() : 0;
        double w30 = f.getWeight30d() != null ? f.getWeight30d().doubleValue() : 0;
        double m = f.getMultiplier() != null ? f.getMultiplier().doubleValue() : 1;
        boolean mul30 = f.getMultiply30() == null || f.getMultiply30() == 1;

        double d7p = d7 > 0 ? (double) d7 / 7.0 : 0;
        double d15p = d15 > 0 ? (double) d15 / 15.0 : 0;
        double d30p = d30 > 0 ? (double) d30 / 30.0 : 0;

        double weighted = d7p * w7 + d15p * w15 + d30p * w30;
        double raw = weighted * m;
        if (mul30) raw = raw * 30.0;

        return Math.max(0, (int) Math.round(raw));
    }

    private static int nvl(Integer v) { return v == null ? 0 : v; }
    private static double nvl(BigDecimal v) { return v == null ? 0 : v.doubleValue(); }

    /** 退货等级 (按顺序命中第一条) */
    static String calcReturnLevel(BigDecimal returnRate, BigDecimal roi, BigDecimal monthlyTurnoverRate)
    {
        double rr = nvl(returnRate) * 100;  // 退货率转百分比: 0.1250 → 12.5
        double r = nvl(roi);                 // ROI 已是百分比: 18.00 = 18%
        double turnover = nvl(monthlyTurnoverRate);  // 月动销率 已是百分比

        // 1
        if (rr > 6) return "问题产品";
        // 2
        if (rr >= 3 && r < 18) return "问题产品";
        // 3
        if (rr < 3 && r < 12 && turnover <= 12) return "问题产品";
        // 4
        if (rr >= 3 && r >= 18) return "长尾产品";
        // 5
        if (rr < 3 && r < 12 && turnover > 12) return "长尾产品";
        // 6
        if (rr < 3 && r >= 12 && r < 22 && turnover < 12) return "长尾产品";
        // 7
        if (rr < 3 && r >= 22 && turnover < 15) return "长尾产品";
        // 8
        if (rr < 3 && r >= 12 && r < 22 && turnover >= 12) return "主力产品";
        // 9
        if (rr < 3 && r >= 22 && turnover >= 15) return "明星产品";

        return "未分类";
    }

    /** 内部库存行 */
    private static class SkuSiteRow
    {
        final String sku;
        final String site;
        int overseasSellable;
        int overseasOnway;
        int localSellable;
        int localOnway;
        int lockNum;

        SkuSiteRow(String sku, String site) { this.sku = sku; this.site = site; }
    }
}
