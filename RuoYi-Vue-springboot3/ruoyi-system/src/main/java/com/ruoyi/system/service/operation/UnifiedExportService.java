package com.ruoyi.system.service.operation;

import java.io.OutputStream;
import java.math.BigDecimal;
import java.util.*;

import jakarta.servlet.http.HttpServletResponse;

import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.streaming.SXSSFWorkbook;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import com.ruoyi.system.domain.operation.*;
import com.ruoyi.system.mapper.operation.*;

@Service
public class UnifiedExportService
{
    @Autowired private AmzReplenishmentSnapshotMapper amzReplenishmentMapper;
    @Autowired private com.ruoyi.system.service.operation.scope.BusinessDataScopeService dataScope;

    public void exportAmzReplenishment(ExportRequest req, HttpServletResponse response) throws Exception
    {
        List<String> allowed = new ArrayList<>(Arrays.asList("sid","sellerSku","warehouseSku","warehouseName","asin","principalName",
            "price","storeName","productCategory","rating","reviewCount","adRate","profitRate30d","refundRate90d",
            "grossProfit30d","grossProfit90d",
            "productNature","purchasedQty","domesticStock","pendingShipQty","fbaStock","fbaInbound","fbaInboundWorking","totalInventory",
            "sales7d","sales14d","sales30d","sales60d","salesSpeed14d","salesSpeed30d","salesSpeed60d",
            "avgMonthlySales","safetyStock","shipQty","replenishQty","restockDays","calcTime"));
        boolean usRegion = req.getFilters() != null && req.getFilters().stream()
                .anyMatch(item -> "regionGroup".equals(item.getField()) && "US".equals(item.getValue()));
        if (usRegion)
        {
            allowed.add("profitRate90d");
        }
        List<String> keys = resolveKeys(req, allowed);
        List<Map<String, Object>> data = fetchAmzReplenishmentData(req, keys);
        writeExcel(response, "Amazon补货数据", data, resolveColumns(req, keys, allowed, amzReplenishmentTitles()));
    }

    // ========== 数据查询 ==========

    private List<Map<String, Object>> fetchAmzReplenishmentData(ExportRequest req, List<String> keys)
    {
        Map<String, Object> params = buildAmzReplenishmentParams(req, 1, 0);
        params.put("businessScope", dataScope.resolve(com.ruoyi.system.service.operation.scope.BusinessDataScopeService.AMZ));
        List<AmzReplenishmentSnapshot> list = amzReplenishmentMapper.search(params);
        List<Map<String, Object>> all = new ArrayList<>();
        Set<String> selected = "SELECTED".equals(req.getScope()) && req.getRowKeys() != null
                ? new HashSet<>(req.getRowKeys()) : null;
        for (AmzReplenishmentSnapshot s : list) {
            if (selected != null && !selected.contains((s.getSid() != null ? s.getSid() : "") + "|" + (s.getSellerSku() != null ? s.getSellerSku() : "") + "|" + (s.getWarehouseSku() != null ? s.getWarehouseSku() : "") + "|" + (s.getWarehouseName() != null ? s.getWarehouseName() : ""))) continue;
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
        // 流式写入：内存只保留 500 行，其余写临时文件，避免数万行时整表驻留内存拖慢导出。
        SXSSFWorkbook wb = new SXSSFWorkbook(500);
        wb.setCompressTempFiles(true);
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
        try
        {
            OutputStream os = response.getOutputStream();
            wb.write(os);
            os.flush();
        }
        finally
        {
            wb.dispose();
            wb.close();
        }
    }

    // ========== 参数构建 ==========

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

    private Map<String, Object> toMap(AmzReplenishmentSnapshot s, List<String> keys)
    {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("sid", s.getSid()); m.put("sellerSku", s.getSellerSku()); m.put("warehouseSku", s.getWarehouseSku());
        m.put("warehouseName", s.getWarehouseName()); m.put("asin", s.getAsin()); m.put("principalName", s.getPrincipalName());
        m.put("price", s.getPrice()); m.put("storeName", s.getStoreName()); m.put("productCategory", s.getProductCategory());
        m.put("productNature", productNatureText(s.getProductNature()));
        m.put("rating", zeroIfNull(s.getRating())); m.put("reviewCount", zeroIfNull(s.getReviewCount()));
        m.put("adRate", formatPercentText(s.getAdRate()));
        m.put("profitRate30d", formatPercentText(s.getProfitRate30d()));
        m.put("grossProfit30d", formatGrossProfit(s.getGrossProfit30d()));
        m.put("grossProfit90d", formatGrossProfit(s.getGrossProfit90d()));
        m.put("refundRate90d", formatPercentText(s.getRefundRate90d()));
        m.put("purchasedQty", s.getPurchasedQty()); m.put("domesticStock", s.getDomesticStock());
        m.put("pendingShipQty", s.getPendingShipQty()); m.put("fbaStock", s.getFbaStock()); m.put("fbaInbound", s.getFbaInbound());
        m.put("fbaInboundWorking", s.getFbaInboundWorking());
        m.put("totalInventory", s.getTotalInventory()); m.put("sales7d", s.getSales7d()); m.put("sales14d", s.getSales14d());
        m.put("sales30d", s.getSales30d()); m.put("sales60d", s.getSales60d()); m.put("salesSpeed14d", s.getSalesSpeed14d());
        m.put("salesSpeed30d", s.getSalesSpeed30d()); m.put("salesSpeed60d", s.getSalesSpeed60d());
        m.put("avgMonthlySales", s.getAvgMonthlySales()); m.put("safetyStock", s.getSafetyStock());
        m.put("shipQty", s.getShipQty()); m.put("replenishQty", s.getReplenishQty()); m.put("restockDays", s.getRestockDays());
        m.put("calcTime", s.getCalcTime());
        m.put("profitRate90d", formatPercentText(s.getProfitRate90d()));
        return filterMap(m, keys);
    }

    private String productNatureText(Integer value)
    {
        if (value == null) return "";
        return value == 2 ? "新品" : "老品";
    }

    private String formatGrossProfit(BigDecimal value)
    {
        return value == null ? "--" : value.setScale(2, java.math.RoundingMode.HALF_UP).toPlainString();
    }

    private Map<String, Object> filterMap(Map<String, Object> m, List<String> keys)
    {
        Map<String, Object> r = new LinkedHashMap<>();
        for (String k : keys) r.put(k, m.get(k));
        return r;
    }

    private String formatPercentText(BigDecimal value)
    {
        if (value == null) return "0";
        if (BigDecimal.ZERO.compareTo(value) == 0) return "0";
        return value.stripTrailingZeros().toPlainString() + "%";
    }

    private Object zeroIfNull(Object value)
    {
        return value != null ? value : "0";
    }

    // ========== 中文标题映射 ==========

    private Map<String, String> amzReplenishmentTitles()
    {
        Map<String, String> t = new LinkedHashMap<>();
        t.put("sid","SID"); t.put("sellerSku","Seller SKU"); t.put("warehouseSku","仓库SKU");
        t.put("warehouseName","仓库"); t.put("asin","ASIN"); t.put("price","价格"); t.put("principalName","负责人"); t.put("storeName","店铺");
        t.put("productCategory","产品分类"); t.put("productNature","产品性质"); t.put("rating","评分"); t.put("reviewCount","评论数");
        t.put("adRate","广告费率"); t.put("profitRate30d","30天利润率"); t.put("refundRate90d","90天退款率");
        t.put("grossProfit30d","30天毛利润（元）"); t.put("grossProfit90d","90天毛利润（元）");
        t.put("purchasedQty","已采购"); t.put("domesticStock","国内仓库存"); t.put("pendingShipQty","待出库");
        t.put("fbaStock","FBA在库"); t.put("fbaInbound","FBA在途"); t.put("fbaInboundWorking","FBA计划入库"); t.put("totalInventory","总库存");
        t.put("sales7d","7天销量"); t.put("sales14d","14天销量"); t.put("sales30d","30天销量"); t.put("sales60d","60天销量");
        t.put("salesSpeed14d","14日均销"); t.put("salesSpeed30d","30日均销"); t.put("salesSpeed60d","60日均销");
        t.put("avgMonthlySales","平均月销量"); t.put("safetyStock","安全库存"); t.put("shipQty","发货量");
        t.put("replenishQty","补货量"); t.put("restockDays","补货时间"); t.put("calcTime","计算时间");
        t.put("profitRate90d","90天利润率");
        return t;
    }
}
