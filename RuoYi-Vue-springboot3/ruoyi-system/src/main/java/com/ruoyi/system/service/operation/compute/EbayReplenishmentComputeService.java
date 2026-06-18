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
            BrandOwnerMapper brandOwnerMapper)
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

        for (EbayProductDedup dedup : dedupMapper.selectAll())
        {
            String rawSku = dedup.getSku();
            if (rawSku == null || (rawSku = rawSku.trim()).isEmpty()) continue;
            String groupKey = InventoryUtils.extractInventoryGroupKey(rawSku);
            if (groupKey.isEmpty()) continue;
            String site = dedup.getSite();
            if (site == null || site.isEmpty()) continue;

            if (!skuProductNameMap.containsKey(groupKey) && dedup.getProductName() != null)
                skuProductNameMap.put(groupKey, dedup.getProductName().trim());

            siteRowsBySku.computeIfAbsent(groupKey, k -> new LinkedHashMap<>())
                    .put(site, new SkuSiteRow(groupKey, site));

            // 利润率
            if (dedup.getProfitRate() != null)
            {
                String mid = InventoryUtils.extractMiddleCodeForInventory(rawSku);
                if (!mid.isEmpty()) profitRateMap.put(site + "|" + mid, dedup.getProfitRate());
            }
            // 退货率
            if (dedup.getReturnRate() != null)
            {
                String mid = InventoryUtils.extractMiddleCodeForInventory(rawSku);
                if (!mid.isEmpty()) returnRateMap.put(site + "|" + mid, dedup.getReturnRate());
            }
        }

        // ---- 2. 库存汇总 (按 groupKey 归并 PC/非PC) ----
        for (WarehouseInventoryDetail d : inventoryMapper.selectAll())
        {
            String baseSku = InventoryUtils.extractInventoryGroupKey(d.getSku());
            if (baseSku.isEmpty()) continue;
            Warehouse wh = warehouseByWid.get(parseIntOrNull(d.getWid()));
            if (wh == null) continue;
            String site = InventoryUtils.whNameToSite(wh.getName());
            if (site.isEmpty()) continue;

            Map<String, SkuSiteRow> sm = siteRowsBySku.get(baseSku);
            if (sm == null) continue;
            SkuSiteRow row = sm.get(site);
            if (row == null) { row = new SkuSiteRow(baseSku, site); sm.put(site, row); }

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

        // ---- 7. 组装结果 ----
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
                String salesKey = row.site + "|" + InventoryUtils.extractMiddleCode(baseSku);
                snap.setSales7d(sa.sales7d.getOrDefault(salesKey, 0));
                snap.setSales30d(sa.sales30d.getOrDefault(salesKey, 0));
                snap.setSales90d(sa.sales90d.getOrDefault(salesKey, 0));
                snap.setMaxMonthlySales(sa.monthlyMax.getOrDefault(salesKey, null));

                // ---- 出库天数 ----
                String mid = InventoryUtils.extractMiddleCode(baseSku);
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

                // ---- 最大月销补货量 = round(maxMonthlySales * 4.03 - totalInventory) ----
                Integer mm = snap.getMaxMonthlySales();
                if (mm != null && mm > 0)
                {
                    snap.setMaxMonthlyReplenishQty((int) Math.round(mm * 4.03 - totalInv));
                }

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
    private Map<String, String> computeOutboundTimes()
    {
        List<GoodcangGrnDetail> allDetails = grnDetailMapper.selectAll();
        Set<String> allCodes = allDetails.stream()
                .map(GoodcangGrnDetail::getReceivingCode)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<String, GoodcangGrnList> grnByCode = new HashMap<>();
        if (!allCodes.isEmpty())
        {
            grnListMapper.selectByReceivingCodes(new ArrayList<>(allCodes))
                    .forEach(g -> grnByCode.put(g.getReceivingCode(), g));
        }

        Set<String> allWhCodes = grnByCode.values().stream()
                .map(GoodcangGrnList::getWarehouseCode)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<String, GoodcangWarehouse> gcWhByCode = new HashMap<>();
        if (!allWhCodes.isEmpty())
        {
            gcWarehouseMapper.selectByWarehouseCodes(new ArrayList<>(allWhCodes))
                    .forEach(g -> gcWhByCode.put(g.getWarehouseCode(), g));
        }

        Map<String, String> result = new LinkedHashMap<>();
        for (GoodcangGrnDetail d : allDetails)
        {
            String mid = InventoryUtils.extractMiddleCodeForInventory(d.getProductSku());
            if (mid.isEmpty() || d.getReceivingCode() == null) continue;
            GoodcangGrnList gl = grnByCode.get(d.getReceivingCode());
            if (gl == null || gl.getWarehouseCode() == null || gl.getCreateAt() == null) continue;
            GoodcangWarehouse gw = gcWhByCode.get(gl.getWarehouseCode());
            if (gw == null || gw.getWid() == null || gw.getWid() == 0) continue;

            String key = mid + "|" + gw.getWid();
            String dt = gl.getCreateAt().toInstant().atZone(ZoneId.systemDefault()).toLocalDate().toString();
            String existing = result.get(key);
            if (existing == null || dt.compareTo(existing) > 0) result.put(key, dt);
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

    private static BigDecimal safeDivide(int a, int b)
    {
        return InventoryUtils.safeDivide(a, b);
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
