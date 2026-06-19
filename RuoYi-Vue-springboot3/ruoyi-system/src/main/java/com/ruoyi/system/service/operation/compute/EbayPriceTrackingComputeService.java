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
 * eBay濮ｅ繑妫╃捄鐔剁幆鐠侊紕鐣诲鏇熸惛閵? * 娴犲孩妫い鍦窗 DailyPriceTrackingServiceImpl.computeDailyPriceTracking() 缁夌粯顦查妴? *
 * 濞翠胶鈻奸敍? *   1. ebay_product_dedup 閳?閸╁搫鍣悰?(site + sku)
 *   2. warehouse_inventory_detail 閳?濞村嘲顦婚崣顖氭暛鎼存挸鐡?type=3)
 *   3. ebay_sales 閳?3/7/30/90婢垛晠鏀㈤柌?+ 閸樺棗褰堕張鈧径褎婀€闁库偓
 *   4. 鐠嬭渹绮?GRN 閳?濞村嘲顦绘禒鎾崇氨姒? *   5. ebay_replenishment_snapshot 閳?妫板嫪鍙婄悰銉ㄦ彛闁?閸栧綊鍘?site + stripPcPrefix(sku))
 *   6. brand_owner 閳?閸濅胶澧?& 閹垮秳缍旈崨? *   7. ebay_link_template 閳?閸烆喖澧?閸烆喖鎮楅柧鐐复(OE閸欓攱娴涢幑?
 *   7. ebay_link_template 閳?閸烆喖澧?閸烆喖鎮楅柧鐐复(OE閸欓攱娴涢幑?
 *   8. ebay_product_dedup 閳?鐠虹喎宕犳禒?閸掆晜榧庨悳?鎼存洜鍤庢禒?閺堚偓娴ｅ簼鐜?婢跺洦鏁?OE閸? *   9. ebay_product_dedup 閳?闁偓鐠愌呭芳閿涘湕xcel鐎电厧鍙嗛敍宀勬姜缂傛牞绶€涙顔岄敍? */
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
        log.info("==== eBay濮ｅ繑妫╃捄鐔剁幆闁插秶鐣?瀵偓婵?====");
        long start = System.currentTimeMillis();

        List<Integer> inventoryWids = parseInventoryWids();
        Map<Integer, Warehouse> warehouseByWid = loadWarehouseMap(inventoryWids);
        Map<Integer, String> widToSite = buildWidToSite(warehouseByWid);

        // ---- 1. 閸╁搫鍣悰?& dedup閺佺増宓?----
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

        // ---- 2. 濞村嘲顦婚崣顖氭暛鎼存挸鐡?type=3) ----
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

        // ---- 3. 闁库偓闁?閸?婢? ----
        SalesAgg sa = aggregateSales();

        // ---- 4. 鐠嬭渹绮ㄩ崙鍝勭氨閺冨爼妫块敍鍫熸崳婢舵牔绮ㄦ惔鎾荤窞閿?----
        Map<String, String> outboundMap = computeOutboundTimes();

        // ---- 5. 閸濅胶澧濈拹鐔荤煑娴?----
        Map<String, String> ownerByBrand = loadBrandOwners();

        // ---- 6. eBay闁剧偓甯村Ο鈩冩緲 ----
        Map<String, EbayLinkTemplate> linkBySite = linkTemplateMapper.selectAll().stream()
                .collect(Collectors.toMap(EbayLinkTemplate::getSite, t -> t, (a, b) -> a));

        // ---- 7. 妫板嫪鍙婄悰銉ㄦ彛闁插骏绱欐禒搴に夌拹褍鎻╅悡褍灏柊宥忕礆 ----
        Map<String, Integer> purchaseQtyMap = new LinkedHashMap<>();
        for (var snap : replenishmentMapper.selectEbayReplenishmentSnapshotList(
                new com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot()))
        {
            if (snap.getSuggestPurchaseQty() != null)
                purchaseQtyMap.put(snap.getSite() + "|" + snap.getSku(), snap.getSuggestPurchaseQty().intValue());
        }

        // ---- 8. 缂佸嫯顥?----
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

                String mid = InventoryUtils.extractMiddleCode(baseSku);
                String salesKey = site + "|" + mid;
                s.setSales3d(sa.sales3d.getOrDefault(salesKey, 0));
                s.setSales7d(sa.sales7d.getOrDefault(salesKey, 0));
                s.setSales30d(sa.sales30d.getOrDefault(salesKey, 0));
                s.setSales90d(sa.sales90d.getOrDefault(salesKey, 0));
                s.setMaxMonthlySales(sa.monthlyMax.getOrDefault(salesKey, null));

                int stock = overseasStockMap.getOrDefault(baseSku + "|" + site, 0);
                s.setOverseasStock(stock);
                s.setStockSalesRatio(safeDivide(stock, s.getSales30d()).multiply(BigDecimal.valueOf(100)).setScale(2, RoundingMode.HALF_UP));

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

                String replenishKey = site + "|" + InventoryUtils.stripPcPrefix(baseSku);
                s.setEstimatedReplenishQty(purchaseQtyMap.get(replenishKey));

                EbayProductDedup dedup = dedupByKey.get(site + "|" + baseSku);
                double profitRate = dedup != null && dedup.getProfitRate() != null ? dedup.getProfitRate().doubleValue() : 0;
                s.setSkuLevel(InventoryUtils.calcProductLevel(s.getSales30d(), profitRate));

                s.setBrandCode(InventoryUtils.extractBrandPrefix(baseSku));
                s.setOperatorName(InventoryUtils.matchOwner(baseSku, ownerByBrand));

                // 闁剧偓甯村Ο鈩冩緲
                EbayLinkTemplate lt = linkBySite.get(site);

                // Editable fields come from ebay_product_dedup.
                if (dedup != null)
                {
                    s.setOeNumber(dedup.getOeNumber());
                    s.setTrackingPrice(dedup.getTrackingPrice());
                    s.setTrackingProfitMargin(dedup.getTrackingProfitMargin());
                    s.setFloorPrice(dedup.getFloorPrice());
                    s.setRemark(dedup.getRemark());
                }

                if (dedup != null) s.setOurLowestPrice(dedup.getLowestPrice());

                if (dedup != null) s.setReturnRate(dedup.getReturnRate());

                // Links use the OE number from ebay_product_dedup.
                String oe = s.getOeNumber() != null ? s.getOeNumber()
                        : (dedup != null ? dedup.getOeNumber() : "");
                if (oe == null) oe = "";
                s.setOeNumber(oe);
                if (lt != null)
                {
                    s.setPresaleUrl(buildUrl(lt.getPresaleUrl(), oe));
                    s.setSoldUrl(buildUrl(lt.getSoldUrl(), oe));
                }

                result.add(s);
            }
        }

        log.info("==== eBay濮ｅ繑妫╃捄鐔剁幆闁插秶鐣?鐎瑰本鍨? {} 閺?閼版妞倇}ms ====", result.size(), System.currentTimeMillis() - start);
        return result;
    }

    // ---- 娴犳挸绨?----
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

    // ---- 闁库偓闁?----
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

    // ---- 閸戝搫绨遍弮鍫曟？閿涘牆鎮撶悰銉ㄦ彛閿?----
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
