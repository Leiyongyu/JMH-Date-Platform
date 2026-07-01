package com.ruoyi.system.service.operation;

import java.io.OutputStream;
import java.util.*;

import jakarta.servlet.http.HttpServletResponse;

import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import com.ruoyi.system.domain.operation.*;
import com.ruoyi.system.mapper.operation.*;

@Service
public class UnifiedExportService
{
    @Autowired private EbayReplenishmentSnapshotMapper ebayReplenishmentMapper;
    @Autowired private EbayPriceTrackingSnapshotMapper ebayPriceTrackingMapper;
    @Autowired private AmzReplenishmentSnapshotMapper amzReplenishmentMapper;

    public void exportEbayReplenishment(ExportRequest req, HttpServletResponse response) throws Exception
    {
        List<String> allowed = Arrays.asList("site","sku","productName","skuLevel","profitRate30d","returnRate",
            "overseasOnway","overseasSellable","overseasTotal","purchasePendingDelivery","localSellable","localOnway",
            "purchasePlanQty","lockedQty","totalInventory","sales7d","sales15d","sales30d","sales90d","maxMonthlySales",
            "monthlySalesForecast",
            "overseasSellableSalesRatio","overseasTotalSalesRatio","totalInventorySalesRatio","lastLocalOutboundTime",
            "outboundDays","purchaseCycleDays","suggestPurchaseQty","maxMonthlyReplenishQty","returnLevel","ownerName");
        List<String> keys = resolveKeys(req, allowed);
        List<Map<String, Object>> data = fetchEbayReplenishmentData(req, keys);
        writeExcel(response, "eBay补货数据", data, resolveColumns(req, keys, allowed, ebayReplenishmentTitles()));
    }

    public void exportEbayPriceTracking(ExportRequest req, HttpServletResponse response) throws Exception
    {
        List<String> allowed = Arrays.asList("site","sku","productName","skuLevel","ourLowestPrice","trackingPrice",
            "trackingProfitMargin","floorPrice","returnRate","sales3d","sales7d","sales30d","sales90d","maxMonthlySales",
            "overseasStock","overseasStockAgeDays","stockSalesRatio","estimatedReplenishQty","brandCode","operatorName",
            "oeNumber","presaleUrl","soldUrl","remark","calcTime");
        List<String> keys = resolveKeys(req, allowed);
        List<Map<String, Object>> data = fetchEbayPriceTrackingData(req, keys);
        writeExcel(response, "eBay每日跟价数据", data, resolveColumns(req, keys, allowed, ebayPriceTrackingTitles()));
    }

    public void exportAmzReplenishment(ExportRequest req, HttpServletResponse response) throws Exception
    {
        List<String> allowed = Arrays.asList("sid","sellerSku","warehouseSku","warehouseName","asin","principalName",
            "price","storeName","productCategory","rating","reviewCount","adRate","profitRate30d","refundRate90d",
            "purchasedQty","domesticStock","pendingShipQty","fbaStock","fbaInbound","totalInventory",
            "sales7d","sales14d","sales30d","sales60d","salesSpeed14d","salesSpeed30d","salesSpeed60d",
            "avgMonthlySales","safetyStock","shipQty","replenishQty","restockDays","calcTime");
        List<String> keys = resolveKeys(req, allowed);
        List<Map<String, Object>> data = fetchAmzReplenishmentData(req, keys);
        writeExcel(response, "Amazon补货数据", data, resolveColumns(req, keys, allowed, amzReplenishmentTitles()));
    }

    // ========== 数据查询 ==========

    private List<Map<String, Object>> fetchEbayReplenishmentData(ExportRequest req, List<String> keys)
    {
        Map<String, Object> params = buildEbayReplenishmentParams(req, 1, 0);
        List<EbayReplenishmentSnapshot> list = ebayReplenishmentMapper.search(params);
        List<Map<String, Object>> all = new ArrayList<>();
        Set<String> selected = "SELECTED".equals(req.getScope()) && req.getRowKeys() != null
                ? new HashSet<>(req.getRowKeys()) : null;
        for (EbayReplenishmentSnapshot s : list) {
            if (selected != null && !selected.contains(s.getSite() + "|" + s.getSku())) continue;
            all.add(toMap(s, keys));
        }
        return all;
    }

    private List<Map<String, Object>> fetchEbayPriceTrackingData(ExportRequest req, List<String> keys)
    {
        Map<String, Object> params = buildEbayPriceTrackingParams(req, 1, 0);
        List<EbayPriceTrackingSnapshot> list = ebayPriceTrackingMapper.search(params);
        List<Map<String, Object>> all = new ArrayList<>();
        Set<String> selected = "SELECTED".equals(req.getScope()) && req.getRowKeys() != null
                ? new HashSet<>(req.getRowKeys()) : null;
        for (EbayPriceTrackingSnapshot s : list) {
            if (selected != null && !selected.contains(s.getSite() + "|" + s.getSku())) continue;
            all.add(toMap(s, keys));
        }
        return all;
    }

    private List<Map<String, Object>> fetchAmzReplenishmentData(ExportRequest req, List<String> keys)
    {
        Map<String, Object> params = buildAmzReplenishmentParams(req, 1, 0);
        List<AmzReplenishmentSnapshot> list = amzReplenishmentMapper.search(params);
        List<Map<String, Object>> all = new ArrayList<>();
        Set<String> selected = "SELECTED".equals(req.getScope()) && req.getRowKeys() != null
                ? new HashSet<>(req.getRowKeys()) : null;
        for (AmzReplenishmentSnapshot s : list) {
            if (selected != null && !selected.contains((s.getSid() != null ? s.getSid() : "") + "|" + (s.getSellerSku() != null ? s.getSellerSku() : "") + "|" + (s.getWarehouseSku() != null ? s.getWarehouseSku() : ""))) continue;
            all.add(toMap(s, keys));
        }
        return all;
    }

    // ========== Excel 导出（流式写入） ==========

    private void writeExcel(HttpServletResponse response, String fileName, List<Map<String, Object>> data, List<ExportRequest.ColumnDef> columns) throws Exception
    {
        response.setContentType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        response.setHeader("Content-Disposition", "attachment; filename=" +
                java.net.URLEncoder.encode(fileName + ".xlsx", "UTF-8"));
        Workbook wb = new XSSFWorkbook();
        Sheet sheet = wb.createSheet(fileName);
        // 表头
        CellStyle headerStyle = wb.createCellStyle();
        Font headerFont = wb.createFont(); headerFont.setBold(true);
        headerStyle.setFont(headerFont);
        Row headerRow = sheet.createRow(0);
        for (int i = 0; i < columns.size(); i++)
        {
            Cell cell = headerRow.createCell(i);
            cell.setCellValue(columns.get(i).getTitle());
            cell.setCellStyle(headerStyle);
        }
        // 数据行
        int rowIdx = 1;
        for (Map<String, Object> row : data)
        {
            Row xr = sheet.createRow(rowIdx++);
            for (int i = 0; i < columns.size(); i++)
            {
                Object v = row.get(columns.get(i).getKey());
                xr.createCell(i).setCellValue(v != null ? String.valueOf(v) : "");
            }
        }
        OutputStream os = response.getOutputStream();
        wb.write(os); wb.close(); os.flush();
    }

    // ========== 参数构建 ==========

    private Map<String, Object> buildEbayReplenishmentParams(ExportRequest req, int page, int size)
    {
        Map<String, Object> p = buildFilterParams(req);
        p.put("sortField", req.getSortField());
        p.put("sortOrder", req.getSortOrder());
        // rowKeys 过滤：site|sku 格式
        if ("SELECTED".equals(req.getScope()) && req.getRowKeys() != null)
            p.put("rowKeys", req.getRowKeys());
        return p;
    }

    private Map<String, Object> buildEbayPriceTrackingParams(ExportRequest req, int page, int size)
    {
        Map<String, Object> p = buildFilterParams(req);
        p.put("sortField", req.getSortField());
        p.put("sortOrder", req.getSortOrder());
        if ("SELECTED".equals(req.getScope()) && req.getRowKeys() != null)
            p.put("rowKeys", req.getRowKeys());
        return p;
    }

    private Map<String, Object> buildAmzReplenishmentParams(ExportRequest req, int page, int size)
    {
        Map<String, Object> p = buildFilterParams(req);
        p.put("sortField", req.getSortField());
        p.put("sortOrder", req.getSortOrder());
        if ("SELECTED".equals(req.getScope()) && req.getRowKeys() != null)
            p.put("rowKeys", req.getRowKeys());
        return p;
    }

    private Map<String, Object> buildFilterParams(ExportRequest req)
    {
        Map<String, Object> p = new HashMap<>();
        if (req.getFilters() != null)
            for (EbayReplenishmentSearchRequest.FilterItem f : req.getFilters())
                if (f.getField() != null && f.getValue() != null)
                    p.put(f.getField(), f.getValue());
        return p;
    }

    // ========== 列配置 ==========

    private List<String> resolveKeys(ExportRequest req, List<String> allowed)
    {
        if (req.getColumns() != null && !req.getColumns().isEmpty())
        {
            List<String> keys = new ArrayList<>();
            for (ExportRequest.ColumnDef c : req.getColumns())
                if (c.getKey() != null && allowed.contains(c.getKey())) keys.add(c.getKey());
            if (!keys.isEmpty()) return keys;
        }
        return allowed;
    }

    private List<ExportRequest.ColumnDef> resolveColumns(ExportRequest req, List<String> keys, List<String> allowed, Map<String, String> titles)
    {
        List<ExportRequest.ColumnDef> cols = new ArrayList<>();
        for (String key : keys)
        {
            ExportRequest.ColumnDef c = new ExportRequest.ColumnDef();
            c.setKey(key); c.setTitle(titles.getOrDefault(key, key));
            cols.add(c);
        }
        return cols;
    }

    // ========== 对象转 Map ==========

    private Map<String, Object> toMap(EbayReplenishmentSnapshot s, List<String> keys)
    {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("site", s.getSite()); m.put("sku", s.getSku()); m.put("productName", s.getProductName());
        m.put("skuLevel", s.getSkuLevel()); m.put("profitRate30d", s.getProfitRate30d()); m.put("returnRate", s.getReturnRate());
        m.put("overseasOnway", s.getOverseasOnway()); m.put("overseasSellable", s.getOverseasSellable());
        m.put("overseasTotal", s.getOverseasTotal()); m.put("purchasePendingDelivery", s.getPurchasePendingDelivery());
        m.put("localSellable", s.getLocalSellable()); m.put("localOnway", s.getLocalOnway());
        m.put("purchasePlanQty", s.getPurchasePlanQty()); m.put("lockedQty", s.getLockedQty());
        m.put("totalInventory", s.getTotalInventory()); m.put("sales7d", s.getSales7d());
        m.put("sales15d", s.getSales15d()); m.put("sales30d", s.getSales30d()); m.put("sales90d", s.getSales90d());
        m.put("maxMonthlySales", s.getMaxMonthlySales()); m.put("monthlySalesForecast", s.getMonthlySalesForecast());
        m.put("overseasSellableSalesRatio", s.getOverseasSellableSalesRatio());
        m.put("overseasTotalSalesRatio", s.getOverseasTotalSalesRatio());
        m.put("totalInventorySalesRatio", s.getTotalInventorySalesRatio());
        m.put("lastLocalOutboundTime", s.getLastLocalOutboundTime()); m.put("outboundDays", s.getOutboundDays());
        m.put("purchaseCycleDays", s.getPurchaseCycleDays()); m.put("suggestPurchaseQty", s.getSuggestPurchaseQty());
        m.put("maxMonthlyReplenishQty", s.getMaxMonthlyReplenishQty()); m.put("returnLevel", s.getReturnLevel()); m.put("ownerName", s.getOwnerName());
        m.put("calcTime", s.getCalcTime());
        return filterMap(m, keys);
    }

    private Map<String, Object> toMap(EbayPriceTrackingSnapshot s, List<String> keys)
    {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("site", s.getSite()); m.put("sku", s.getSku()); m.put("productName", s.getProductName());
        m.put("skuLevel", s.getSkuLevel()); m.put("ourLowestPrice", s.getOurLowestPrice());
        m.put("trackingPrice", s.getTrackingPrice()); m.put("trackingProfitMargin", s.getTrackingProfitMargin());
        m.put("floorPrice", s.getFloorPrice()); m.put("returnRate", s.getReturnRate());
        m.put("sales3d", s.getSales3d()); m.put("sales7d", s.getSales7d()); m.put("sales30d", s.getSales30d());
        m.put("sales90d", s.getSales90d()); m.put("maxMonthlySales", s.getMaxMonthlySales());
        m.put("overseasStock", s.getOverseasStock()); m.put("overseasStockAgeDays", s.getOverseasStockAgeDays());
        m.put("stockSalesRatio", s.getStockSalesRatio()); m.put("estimatedReplenishQty", s.getEstimatedReplenishQty());
        m.put("brandCode", s.getBrandCode()); m.put("operatorName", s.getOperatorName());
        m.put("oeNumber", s.getOeNumber()); m.put("presaleUrl", s.getPresaleUrl()); m.put("soldUrl", s.getSoldUrl());
        m.put("remark", s.getRemark()); m.put("calcTime", s.getCalcTime());
        return filterMap(m, keys);
    }

    private Map<String, Object> toMap(AmzReplenishmentSnapshot s, List<String> keys)
    {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("sid", s.getSid()); m.put("sellerSku", s.getSellerSku()); m.put("warehouseSku", s.getWarehouseSku());
        m.put("warehouseName", s.getWarehouseName()); m.put("asin", s.getAsin()); m.put("principalName", s.getPrincipalName());
        m.put("price", s.getPrice()); m.put("storeName", s.getStoreName()); m.put("productCategory", s.getProductCategory());
        m.put("rating", s.getRating()); m.put("reviewCount", s.getReviewCount()); m.put("adRate", s.getAdRate());
        m.put("profitRate30d", s.getProfitRate30d()); m.put("refundRate90d", s.getRefundRate90d());
        m.put("purchasedQty", s.getPurchasedQty()); m.put("domesticStock", s.getDomesticStock());
        m.put("pendingShipQty", s.getPendingShipQty()); m.put("fbaStock", s.getFbaStock()); m.put("fbaInbound", s.getFbaInbound());
        m.put("totalInventory", s.getTotalInventory()); m.put("sales7d", s.getSales7d()); m.put("sales14d", s.getSales14d());
        m.put("sales30d", s.getSales30d()); m.put("sales60d", s.getSales60d()); m.put("salesSpeed14d", s.getSalesSpeed14d());
        m.put("salesSpeed30d", s.getSalesSpeed30d()); m.put("salesSpeed60d", s.getSalesSpeed60d());
        m.put("avgMonthlySales", s.getAvgMonthlySales()); m.put("safetyStock", s.getSafetyStock());
        m.put("shipQty", s.getShipQty()); m.put("replenishQty", s.getReplenishQty()); m.put("restockDays", s.getRestockDays());
        m.put("calcTime", s.getCalcTime());
        return filterMap(m, keys);
    }

    private Map<String, Object> filterMap(Map<String, Object> m, List<String> keys)
    {
        Map<String, Object> r = new LinkedHashMap<>();
        for (String k : keys) r.put(k, m.get(k));
        return r;
    }

    // ========== 中文标题映射 ==========

    private Map<String, String> ebayReplenishmentTitles()
    {
        Map<String, String> t = new LinkedHashMap<>();
        t.put("site","站点"); t.put("sku","SKU"); t.put("productName","产品名称"); t.put("skuLevel","等级");
        t.put("profitRate30d","近30天利润"); t.put("returnRate","退货率"); t.put("overseasOnway","海外在途");
        t.put("overseasSellable","海外可售"); t.put("overseasTotal","海外总库存"); t.put("purchasePendingDelivery","采购待交付");
        t.put("localSellable","成都可售"); t.put("localOnway","成都在途"); t.put("purchasePlanQty","采购计划");
        t.put("lockedQty","待出库"); t.put("totalInventory","总库存"); t.put("sales7d","近7天销量");
        t.put("sales30d","近30天销量"); t.put("sales90d","近90天销量"); t.put("maxMonthlySales","历史最大月销");
        t.put("monthlySalesForecast","月销预测");
        t.put("overseasSellableSalesRatio","海外在库库销比"); t.put("overseasTotalSalesRatio","海外总库销比");
        t.put("totalInventorySalesRatio","总库存库销比"); t.put("lastLocalOutboundTime","最近本地出库");
        t.put("outboundDays","出库天数"); t.put("purchaseCycleDays","采购周期"); t.put("suggestPurchaseQty","采购数量");
        t.put("maxMonthlyReplenishQty","最大月销补货量"); t.put("returnLevel","退货等级"); t.put("ownerName","负责人");
        return t;
    }

    private Map<String, String> ebayPriceTrackingTitles()
    {
        Map<String, String> t = new LinkedHashMap<>();
        t.put("site","站点"); t.put("sku","SKU"); t.put("productName","产品名称"); t.put("skuLevel","等级");
        t.put("ourLowestPrice","最低价"); t.put("trackingPrice","跟卖价"); t.put("trackingProfitMargin","跟卖利润率");
        t.put("floorPrice","底线价"); t.put("returnRate","退货率"); t.put("sales3d","近3天销量");
        t.put("sales7d","近7天销量"); t.put("sales15d","近15天销量"); t.put("sales30d","近30天销量"); t.put("sales90d","近90天销量");
        t.put("maxMonthlySales","历史最大月销"); t.put("overseasStock","海外仓库存");
        t.put("overseasStockAgeDays","海外仓库龄"); t.put("stockSalesRatio","库销比");
        t.put("estimatedReplenishQty","预估补货量"); t.put("brandCode","品牌"); t.put("operatorName","操作员");
        t.put("oeNumber","OE号"); t.put("presaleUrl","售前链接"); t.put("soldUrl","售后链接");
        t.put("remark","备注"); t.put("calcTime","计算时间");
        return t;
    }

    private Map<String, String> amzReplenishmentTitles()
    {
        Map<String, String> t = new LinkedHashMap<>();
        t.put("sid","SID"); t.put("sellerSku","Seller SKU"); t.put("warehouseSku","仓库SKU");
        t.put("warehouseName","仓库"); t.put("asin","ASIN"); t.put("price","价格"); t.put("principalName","负责人"); t.put("storeName","店铺");
        t.put("productCategory","产品分类"); t.put("rating","评分"); t.put("reviewCount","评论数");
        t.put("adRate","广告费率"); t.put("profitRate30d","30天利润率"); t.put("refundRate90d","90天退款率");
        t.put("purchasedQty","已采购"); t.put("domesticStock","国内仓库存"); t.put("pendingShipQty","待出库");
        t.put("fbaStock","FBA在库"); t.put("fbaInbound","FBA在途"); t.put("totalInventory","总库存");
        t.put("sales7d","7天销量"); t.put("sales14d","14天销量"); t.put("sales30d","30天销量"); t.put("sales60d","60天销量");
        t.put("salesSpeed14d","14日均销"); t.put("salesSpeed30d","30日均销"); t.put("salesSpeed60d","60日均销");
        t.put("avgMonthlySales","平均月销量"); t.put("safetyStock","安全库存"); t.put("shipQty","发货量");
        t.put("replenishQty","补货量"); t.put("restockDays","补货时间"); t.put("calcTime","计算时间");
        return t;
    }
}
