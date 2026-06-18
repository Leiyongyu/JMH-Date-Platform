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

import com.ruoyi.system.domain.operation.EbayPriceTrackingSnapshot;
import com.ruoyi.system.domain.operation.external.*;
import com.ruoyi.system.mapper.operation.EbayReplenishmentSnapshotMapper;
import com.ruoyi.system.mapper.operation.external.*;
import com.ruoyi.system.service.operation.external.lingxing.LingxingProperties;

/**
 * eBay每日跟价计算引擎。
 * 从旧项目 DailyPriceTrackingServiceImpl.computeDailyPriceTracking() 移植。
 *
 * 流程：
 *   1. ebay_product_dedup → 基准行 (site + sku)
 *   2. warehouse_inventory_detail → 海外可售库存(type=3)
 *   3. ebay_sales → 3/7/30/90天销量 + 历史最大月销
 *   4. 谷仓 GRN → 海外仓库龄
 *   5. ebay_replenishment_snapshot → 预估补货量(匹配 site + stripPcPrefix(sku))
 *   6. brand_owner → 品牌 & 操作员
 *   7. ebay_link_template → 售前/售后链接(OE号替换)
 *   8. ebay_product_dedup → 跟卖价/利润率/底线价/最低价/备注/OE号（实时补充）
 */
@Service
public class EbayPriceTrackingComputeService
{
    private static final Logger log = LoggerFactory.getLogger(EbayPriceTrackingComputeService.class);

    private final LingxingProperties lingxingProperties;
    private final WarehouseMapper warehouseMapper;
    private final WarehouseInventoryDetailMapper inventoryMapper;
    private final EbayProductDedupMapper dedupMapper;
    private final EbaySalesMapper ebaySalesMapper;
    private final GoodcangGrnListMapper grnListMapper;
    private final GoodcangGrnDetailMapper grnDetailMapper;
    private final GoodcangWarehouseMapper gcWarehouseMapper;
    private final BrandOwnerMapper brandOwnerMapper;
    private final EbayLinkTemplateMapper linkTemplateMapper;
    private final EbayReplenishmentSnapshotMapper replenishmentMapper;

    public EbayPriceTrackingComputeService(
            LingxingProperties lingxingProperties,
            WarehouseMapper warehouseMapper,
            WarehouseInventoryDetailMapper inventoryMapper,
            EbayProductDedupMapper dedupMapper,
            EbaySalesMapper ebaySalesMapper,
            GoodcangGrnListMapper grnListMapper,
            GoodcangGrnDetailMapper grnDetailMapper,
            GoodcangWarehouseMapper gcWarehouseMapper,
            BrandOwnerMapper brandOwnerMapper,
            EbayLinkTemplateMapper linkTemplateMapper,
            EbayReplenishmentSnapshotMapper replenishmentMapper)
    {
        this.lingxingProperties = lingxingProperties;
        this.warehouseMapper = warehouseMapper;
        this.inventoryMapper = inventoryMapper;
        this.dedupMapper = dedupMapper;
        this.ebaySalesMapper = ebaySalesMapper;
        this.grnListMapper = grnListMapper;
        this.grnDetailMapper = grnDetailMapper;
        this.gcWarehouseMapper = gcWarehouseMapper;
        this.brandOwnerMapper = brandOwnerMapper;
        this.linkTemplateMapper = linkTemplateMapper;
        this.replenishmentMapper = replenishmentMapper;
    }

    public List<EbayPriceTrackingSnapshot> compute()
    {
        log.info("==== eBay每日跟价重算 开始 ====");
        long start = System.currentTimeMillis();

        List<Integer> inventoryWids = parseInventoryWids();
        Map<Integer, Warehouse> warehouseByWid = loadWarehouseMap(inventoryWids);
        Map<Integer, String> widToSite = buildWidToSite(warehouseByWid);

        // ---- 1. 基准行 & dedup数据 ----
        Map<String, EbayProductDedup> dedupByKey = new LinkedHashMap<>();
        Map<String, String> skuProductName = new LinkedHashMap<>();
        Map<String, Set<String>> skuSites = new LinkedHashMap<>();

        for (EbayProductDedup d : dedupMapper.selectAll())
        {
            String sku = d.getSku(), site = d.getSite();
            if (sku == null || sku.isEmpty() || site == null || site.isEmpty()) continue;
            String key = site + "|" + sku;
            dedupByKey.put(key, d);
            skuProductName.putIfAbsent(sku, d.getProductName() != null ? d.getProductName().trim() : "");
            skuSites.computeIfAbsent(sku, k -> new LinkedHashSet<>()).add(site);
        }

        // ---- 2. 海外可售库存(type=3) ----
        Map<String, Integer> overseasStockMap = new LinkedHashMap<>();
        for (WarehouseInventoryDetail d : inventoryMapper.selectAll())
        {
            Warehouse wh = warehouseByWid.get(parseIntOrNull(d.getWid()));
            if (wh == null || wh.getType() == null || wh.getType() != 3) continue;
            String baseSku = InventoryUtils.extractBaseSku(d.getSku());
            if (baseSku.isEmpty()) continue;
            String site = widToSite.getOrDefault(parseIntOrNull(d.getWid()), "");
            if (site.isEmpty()) continue;
            overseasStockMap.merge(baseSku + "|" + site, d.getProductValidNum(), Integer::sum);
        }

        // ---- 3. 销量(含3天) ----
        SalesAgg sa = aggregateSales();

        // ---- 4. 谷仓出库时间（海外仓库龄） ----
        Map<String, String> outboundMap = computeOutboundTimes();

        // ---- 5. 品牌负责人 ----
        Map<String, String> ownerByBrand = loadBrandOwners();

        // ---- 6. eBay链接模板 ----
        Map<String, EbayLinkTemplate> linkBySite = linkTemplateMapper.selectAll().stream()
                .collect(Collectors.toMap(EbayLinkTemplate::getSite, t -> t, (a, b) -> a));

        // ---- 7. 预估补货量（从补货快照匹配） ----
        Map<String, Integer> purchaseQtyMap = new LinkedHashMap<>();
        for (var snap : replenishmentMapper.selectEbayReplenishmentSnapshotList(
                new com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot()))
        {
            if (snap.getSuggestPurchaseQty() != null)
                purchaseQtyMap.put(snap.getSite() + "|" + snap.getSku(), snap.getSuggestPurchaseQty().intValue());
        }

        // ---- 8. 组装 ----
        LocalDate today = LocalDate.now();
        List<EbayPriceTrackingSnapshot> result = new ArrayList<>();

        for (Map.Entry<String, Set<String>> e : skuSites.entrySet())
        {
            String baseSku = e.getKey();
            for (String site : e.getValue())
            {
                EbayPriceTrackingSnapshot s = new EbayPriceTrackingSnapshot();
                s.setSite(site);
                s.setSku(baseSku);
                s.setProductName(skuProductName.getOrDefault(baseSku, ""));

                // 销量
                String mid = InventoryUtils.extractMiddleCode(baseSku);
                String salesKey = site + "|" + mid;
                s.setSales3d(sa.sales3d.getOrDefault(salesKey, 0));
                s.setSales7d(sa.sales7d.getOrDefault(salesKey, 0));
                s.setSales30d(sa.sales30d.getOrDefault(salesKey, 0));
                s.setSales90d(sa.sales90d.getOrDefault(salesKey, 0));
                s.setMaxMonthlySales(sa.monthlyMax.getOrDefault(salesKey, null));

                // 海外库存 & 库销比
                int stock = overseasStockMap.getOrDefault(baseSku + "|" + site, 0);
                s.setOverseasStock(stock);
                s.setStockSalesRatio(safeDivide(stock, s.getSales30d()).multiply(BigDecimal.valueOf(100)).setScale(2, RoundingMode.HALF_UP));

                // 海外仓库龄
                if (!mid.isEmpty())
                {
                    String latestTime = null;
                    for (Map.Entry<Integer, String> we : widToSite.entrySet())
                    {
                        if (site.equals(we.getValue()))
                        {
                            String t = outboundMap.get(mid + "|" + we.getKey());
                            if (t != null && (latestTime == null || t.compareTo(latestTime) > 0)) latestTime = t;
                        }
                    }
                    if (latestTime != null)
                    {
                        try { s.setOverseasStockAgeDays((int) ChronoUnit.DAYS.between(LocalDate.parse(latestTime), today)); }
                        catch (Exception ignored) {}
                    }
                }

                // 预估补货量
                String replenishKey = site + "|" + InventoryUtils.stripPcPrefix(baseSku);
                s.setEstimatedReplenishQty(purchaseQtyMap.get(replenishKey));

                // SKU等级（从补货快照取利润率）
                // 利润率从 ebay_product_dedup 取
                EbayProductDedup dedup = dedupByKey.get(site + "|" + baseSku);
                double profitRate = dedup != null && dedup.getProfitRate() != null ? dedup.getProfitRate().doubleValue() : 0;
                s.setSkuLevel(InventoryUtils.calcProductLevel(s.getSales30d(), profitRate));

                // 品牌 & 操作员
                s.setBrandCode(InventoryUtils.extractBrandPrefix(baseSku));
                s.setOperatorName(InventoryUtils.matchOwner(baseSku, ownerByBrand));

                // 链接模板
                EbayLinkTemplate lt = linkBySite.get(site);
                String oe = dedup != null ? dedup.getOeNumber() : "";
                s.setOeNumber(oe);
                if (lt != null)
                {
                    s.setPresaleUrl(buildUrl(lt.getPresaleUrl(), oe));
                    s.setSoldUrl(buildUrl(lt.getSoldUrl(), oe));
                }

                // 从 ebay_product_dedup 取：跟卖价/利润率/底线价/最低价/退货率/备注
                if (dedup != null)
                {
                    s.setTrackingPrice(dedup.getTrackingPrice());
                    s.setTrackingProfitMargin(dedup.getTrackingProfitMargin());
                    s.setFloorPrice(dedup.getFloorPrice());
                    s.setOurLowestPrice(dedup.getLowestPrice());
                    s.setReturnRate(dedup.getReturnRate());
                    s.setRemark(dedup.getRemark());
                }

                result.add(s);
            }
        }

        log.info("==== eBay每日跟价重算 完成: {} 条 耗时{}ms ====", result.size(), System.currentTimeMillis() - start);
        return result;
    }

    // ---- 仓库 ----
    private List<Integer> parseInventoryWids()
    {
        List<Integer> list = new ArrayList<>();
        String raw = lingxingProperties.getInventoryWids();
        if (StringUtils.hasText(raw))
            for (String p : raw.split(","))
                try { list.add(Integer.parseInt(p.trim())); } catch (NumberFormatException ignored) {}
        return list;
    }

    private Map<Integer, Warehouse> loadWarehouseMap(List<Integer> wids)
    {
        return warehouseMapper.selectAll().stream()
                .filter(w -> w.getWid() != null && wids.contains(w.getWid()) && w.getWid() != 1194)
                .collect(Collectors.toMap(Warehouse::getWid, w -> w, (a, b) -> a));
    }

    private Map<Integer, String> buildWidToSite(Map<Integer, Warehouse> wm)
    {
        Map<Integer, String> m = new HashMap<>();
        wm.forEach((k, v) -> m.put(k, InventoryUtils.whNameToSite(v.getName())));
        return m;
    }

    // ---- 销量 ----
    private SalesAgg aggregateSales()
    {
        SalesAgg agg = new SalesAgg();
        LocalDate today = LocalDate.now();
        LocalDate c3 = today.minusDays(3), c7 = today.minusDays(7), c30 = today.minusDays(30), c90 = today.minusDays(90);

        for (EbaySales s : ebaySalesMapper.selectAll())
        {
            String sku = s.getSku(), cur = s.getCurrency();
            if (sku == null || sku.isEmpty() || cur == null || cur.isEmpty()) continue;
            String mid = InventoryUtils.extractMiddleCodeForInventory(sku);
            if (mid.isEmpty()) continue;
            String site = InventoryUtils.currencyToSite(cur.toUpperCase());
            if (site.isEmpty()) continue;
            LocalDate pd = s.getPaymentTime() != null
                    ? s.getPaymentTime().toInstant().atZone(ZoneId.systemDefault()).toLocalDate() : null;
            if (pd == null) continue;
            int qty = s.getQuantity() != null ? s.getQuantity() : 0;
            String key = site + "|" + mid;

            if (!pd.isBefore(c3)) agg.sales3d.merge(key, qty, Integer::sum);
            if (!pd.isBefore(c7)) agg.sales7d.merge(key, qty, Integer::sum);
            if (!pd.isBefore(c30)) agg.sales30d.merge(key, qty, Integer::sum);
            if (!pd.isBefore(c90)) agg.sales90d.merge(key, qty, Integer::sum);

            String mk = pd.getYear() + "-" + String.format("%02d", pd.getMonthValue());
            agg.monthly.computeIfAbsent(key, k -> new LinkedHashMap<>()).merge(mk, qty, Integer::sum);
        }
        for (Map.Entry<String, Map<String, Integer>> e : agg.monthly.entrySet())
            agg.monthlyMax.put(e.getKey(), e.getValue().values().stream().max(Integer::compareTo).orElse(0));
        return agg;
    }

    private static class SalesAgg
    {
        Map<String, Integer> sales3d = new LinkedHashMap<>();
        Map<String, Integer> sales7d = new LinkedHashMap<>();
        Map<String, Integer> sales30d = new LinkedHashMap<>();
        Map<String, Integer> sales90d = new LinkedHashMap<>();
        Map<String, Map<String, Integer>> monthly = new LinkedHashMap<>();
        Map<String, Integer> monthlyMax = new LinkedHashMap<>();
    }

    // ---- 出库时间（同补货） ----
    private Map<String, String> computeOutboundTimes()
    {
        List<GoodcangGrnDetail> all = grnDetailMapper.selectAll();
        Set<String> codes = all.stream().map(GoodcangGrnDetail::getReceivingCode).filter(Objects::nonNull).collect(Collectors.toSet());
        Map<String, GoodcangGrnList> grnByCode = new HashMap<>();
        if (!codes.isEmpty()) grnListMapper.selectByReceivingCodes(new ArrayList<>(codes)).forEach(g -> grnByCode.put(g.getReceivingCode(), g));
        Set<String> whCodes = grnByCode.values().stream().map(GoodcangGrnList::getWarehouseCode).filter(Objects::nonNull).collect(Collectors.toSet());
        Map<String, GoodcangWarehouse> gcWh = new HashMap<>();
        if (!whCodes.isEmpty()) gcWarehouseMapper.selectByWarehouseCodes(new ArrayList<>(whCodes)).forEach(g -> gcWh.put(g.getWarehouseCode(), g));

        Map<String, String> r = new LinkedHashMap<>();
        for (GoodcangGrnDetail d : all)
        {
            String mid = InventoryUtils.extractMiddleCodeForInventory(d.getProductSku());
            if (mid.isEmpty() || d.getReceivingCode() == null) continue;
            GoodcangGrnList gl = grnByCode.get(d.getReceivingCode());
            if (gl == null || gl.getWarehouseCode() == null || gl.getCreateAt() == null) continue;
            GoodcangWarehouse gw = gcWh.get(gl.getWarehouseCode());
            if (gw == null || gw.getWid() == null || gw.getWid() == 0) continue;
            String key = mid + "|" + gw.getWid();
            String dt = gl.getCreateAt().toInstant().atZone(ZoneId.systemDefault()).toLocalDate().toString();
            String ex = r.get(key);
            if (ex == null || dt.compareTo(ex) > 0) r.put(key, dt);
        }
        return r;
    }

    private Map<String, String> loadBrandOwners()
    {
        return brandOwnerMapper.selectAll().stream().collect(Collectors.toMap(
                b -> StringUtils.hasText(b.getBrandCode()) ? b.getBrandCode().trim().toUpperCase() : "",
                b -> StringUtils.hasText(b.getOwnerName()) ? b.getOwnerName().trim() : "", (a, b2) -> a));
    }

    private String buildUrl(String template, String oe)
    {
        if (template == null) return "";
        return template.replace("{oe}", oe != null ? oe : "");
    }

    private static Integer parseIntOrNull(String s) { try { return Integer.parseInt(s); } catch (Exception e) { return null; } }
    private static BigDecimal safeDivide(int a, int b) { return InventoryUtils.safeDivide(a, b); }
}
