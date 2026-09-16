package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.operation.ebay.EbayInventoryDetailPythonClient;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 运营中心 / eBay / 库存明细；列表、等级导入与导出使用独立权限。 */
@RestController
@RequestMapping("/finance/ebay-inventory-detail")
public class EbayInventoryDetailController extends BaseController
{
    private final EbayInventoryDetailPythonClient client;

    public EbayInventoryDetailController(EbayInventoryDetailPythonClient client)
    {
        this.client = client;
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayInventoryDetail:list')")
    @GetMapping("/list")
    public AjaxResult list(
            @RequestParam(required = false) String site,
            @RequestParam(required = false) String sku,
            @RequestParam(required = false) String brand,
            @RequestParam(required = false) String grade,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "50") int pageSize,
            @RequestParam(required = false) String sortField,
            @RequestParam(required = false) String sortOrder,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> params = filters(site, sku, brand, grade, sortField, sortOrder);
        params.put("page", Math.max(1, pageNum));
        params.put("page_size", Math.min(200, Math.max(1, pageSize)));
        return success(client.list(params, requestId).get("data"));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayInventoryDetail:export')")
    @Log(title = "Ebay库存明细导出", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(
            @RequestBody(required = false) Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            HttpServletResponse response) throws IOException
    {
        Map<String, Object> input = body == null ? Map.of() : body;
        Map<String, Object> payload = filters(text(input.get("site")), text(input.get("sku")),
                text(input.get("brand")), text(input.get("grade")),
                text(input.get("sortField")), text(input.get("sortOrder")));
        // 只传主键，不接收客户端金额；Python 按同一查询逻辑重新取数并校验。
        payload.put("selected_keys", input.getOrDefault("selectedKeys", List.of()));
        // 导出始终包含全部27个业务字段；列抽屉只调整页面显示。
        EbayInventoryDetailPythonClient.ExcelFile file = client.export(payload, requestId);
        sendExcel(file, response);
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayInventoryDetail:list')")
    @GetMapping("/pivot")
    public AjaxResult pivot(
            @RequestParam(required = false) String startDate,
            @RequestParam(required = false) String endDate,
            @RequestParam(required = false) String owner,
            @RequestParam(required = false) String site,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "50") int pageSize,
            @RequestParam(required = false) String sortField,
            @RequestParam(required = false) String sortOrder,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> params = pivotFilters(startDate, endDate, owner, site, sortField, sortOrder);
        params.put("page", Math.max(1, pageNum));
        params.put("page_size", Math.min(200, Math.max(1, pageSize)));
        return success(client.pivot(params, requestId).get("data"));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayInventoryDetail:export')")
    @Log(title = "Ebay库存历史透视导出", businessType = BusinessType.EXPORT)
    @GetMapping("/pivot/export")
    public void exportPivot(
            @RequestParam(required = false) String startDate,
            @RequestParam(required = false) String endDate,
            @RequestParam(required = false) String owner,
            @RequestParam(required = false) String site,
            @RequestParam(required = false) String sortField,
            @RequestParam(required = false) String sortOrder,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            HttpServletResponse response) throws IOException
    {
        // 不传分页参数：导出全部符合日期、负责人和站点筛选的历史统计行。
        sendExcel(client.exportPivot(pivotFilters(startDate, endDate, owner, site, sortField, sortOrder),
                requestId), response);
    }

    private static void sendExcel(EbayInventoryDetailPythonClient.ExcelFile file,
            HttpServletResponse response) throws IOException
    {
        response.setContentType(EbayInventoryDetailPythonClient.EXCEL_CONTENT_TYPE);
        response.setHeader("Content-Disposition", file.contentDisposition());
        response.setHeader("Access-Control-Expose-Headers", "Content-Disposition");
        response.setHeader("Cache-Control", "no-store");
        response.setContentLengthLong(file.content().length);
        response.getOutputStream().write(file.content());
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayInventoryDetail:import')")
    @Log(title = "Ebay库存明细产品等级导入", businessType = BusinessType.IMPORT)
    @PostMapping("/grades/import")
    public AjaxResult importGrades(@RequestParam("file") MultipartFile file,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(client.importGrades(file, getUsername(), requestId).get("data"));
    }

    private static Map<String, Object> filters(String site, String sku, String brand,
            String grade, String sortField, String sortOrder)
    {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("site", text(site));
        values.put("sku", text(sku));
        values.put("brand", text(brand));
        values.put("grade", text(grade));
        values.put("sort_field", text(sortField));
        values.put("sort_order", text(sortOrder));
        return values;
    }

    private static Map<String, Object> pivotFilters(String startDate, String endDate, String owner,
            String site, String sortField, String sortOrder)
    {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("start_date", text(startDate));
        values.put("end_date", text(endDate));
        values.put("owner", text(owner));
        values.put("site", text(site));
        values.put("sort_field", text(sortField));
        values.put("sort_order", text(sortOrder));
        return values;
    }

    private static String text(Object value)
    {
        if (value == null) return null;
        String result = String.valueOf(value).trim();
        return StringUtils.hasText(result) ? result : null;
    }
}
