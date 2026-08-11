package com.ruoyi.web.controller.sop;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** SOP-AMZ售后数据，统一代理Python ETL及查询服务。 */
@Tag(name = "SOP售后数据")
@RestController
@RequestMapping("/sop/after-sales")
public class AmzSopAfterSalesController extends BaseController
{
    private final PerformancePythonClient pythonClient;
    private final PythonPerformanceSchedulerClient schedulerClient;

    public AmzSopAfterSalesController(
            PerformancePythonClient pythonClient,
            PythonPerformanceSchedulerClient schedulerClient)
    {
        this.pythonClient = pythonClient;
        this.schedulerClient = schedulerClient;
    }

    @PreAuthorize("@ss.hasPermi('sop:afterSales:list')")
    @GetMapping("/list")
    public AjaxResult list(
            @RequestParam(defaultValue = "amz") String platform,
            @RequestParam(required = false) String startDate,
            @RequestParam(required = false) String endDate,
            @RequestParam(required = false) String bigCategory,
            @RequestParam(required = false) String smallCategory,
            @RequestParam(required = false) String sku,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "20") int pageSize,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try
        {
            Map<String, Object> params = new LinkedHashMap<>();
            params.put("start_date", startDate);
            params.put("end_date", endDate);
            params.put("big_category", bigCategory);
            params.put("small_category", smallCategory);
            params.put("sku", sku);
            params.put("page", pageNum);
            params.put("page_size", pageSize);
            Map<String, Object> response = isEbay(platform)
                    ? pythonClient.ebaySopAfterSalesSummary(params, requestId)
                    : pythonClient.amzSopAfterSalesSummary(params, requestId);
            Map<String, Object> data = map(response.get("data"));
            Object items = data.get("items");
            return AjaxResult.success()
                    .put("rows", items instanceof List<?> ? items : List.of())
                    .put("total", data.getOrDefault("total", 0))
                    .put("periodStart", data.get("period_start"))
                    .put("periodEnd", data.get("period_end"))
                    .put("rangeGenerated", data.getOrDefault("range_generated", false))
                    .put("rangeStatus", data.getOrDefault("range_status", "ready"))
                    .put("rangeMessage", data.getOrDefault("range_message", ""))
                    .put("summary", data.getOrDefault("summary", Map.of()))
                    .put("requestId", response.get("request_id"));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('sop:afterSales:list')")
    @GetMapping("/categories")
    public AjaxResult categories(
            @RequestParam(defaultValue = "amz") String platform,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try
        {
            Map<String, Object> response = isEbay(platform)
                    ? pythonClient.ebaySopAfterSalesCategories(requestId)
                    : pythonClient.amzSopAfterSalesCategories(requestId);
            return success(response.get("data"));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('sop:afterSales:list')")
    @GetMapping("/periods")
    public AjaxResult periods(
            @RequestParam(defaultValue = "amz") String platform,
            @RequestParam(defaultValue = "24") int limit,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try
        {
            Map<String, Object> response = isEbay(platform)
                    ? pythonClient.ebaySopAfterSalesPeriods(limit, requestId)
                    : pythonClient.amzSopAfterSalesPeriods(limit, requestId);
            return success(response.get("data"));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "AMZ-SOP售后链路手工补跑", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('sop:afterSales:sync')")
    @PostMapping("/sync")
    public AjaxResult sync(
            @RequestParam(required = false) String startDate,
            @RequestParam(required = false) String endDate,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (StringUtils.hasText(startDate) != StringUtils.hasText(endDate))
            return error("开始日期和结束日期必须同时填写");
        try
        {
            return success(schedulerClient.runAmzSop(
                    startDate, endDate, requestId, "MANUAL"));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "SOP售后表导出", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('sop:afterSales:export')")
    @GetMapping("/export")
    public ResponseEntity<byte[]> export(
            @RequestParam(defaultValue = "amz") String platform,
            @RequestParam String startDate,
            @RequestParam String endDate,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        boolean ebay = isEbay(platform);
        byte[] file = ebay
                ? pythonClient.exportEbaySopAfterSales(startDate, endDate, requestId)
                : pythonClient.exportAmzSopAfterSales(startDate, endDate, requestId);
        String timestamp = LocalDateTime.now().format(
                DateTimeFormatter.ofPattern("yyyyMMddHHmmss"));
        String filename = URLEncoder.encode(
                (ebay ? "eBay" : "AMZ") + "-SOP售后表-" + startDate + "-" + endDate
                        + "-" + timestamp + ".xlsx",
                StandardCharsets.UTF_8).replace("+", "%20");
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename*=UTF-8''" + filename)
                .contentType(MediaType.parseMediaType(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                .contentLength(file.length)
                .body(file);
    }

    @Log(title = "SOP售后数据导出", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('sop:afterSales:export')")
    @GetMapping("/export-data")
    public ResponseEntity<byte[]> exportData(
            @RequestParam(defaultValue = "amz") String platform,
            @RequestParam String startDate,
            @RequestParam String endDate,
            @RequestParam(required = false) String bigCategory,
            @RequestParam(required = false) String smallCategory,
            @RequestParam(required = false) String sku,
            @RequestParam(required = false) String ids,
            @RequestParam(required = false) String skus,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("start_date", startDate);
        params.put("end_date", endDate);
        params.put("big_category", bigCategory);
        params.put("small_category", smallCategory);
        params.put("sku", sku);
        params.put("ids", ids);
        params.put("skus", skus);
        boolean ebay = isEbay(platform);
        byte[] file = ebay
                ? pythonClient.exportEbaySopAfterSalesData(params, requestId)
                : pythonClient.exportAmzSopAfterSalesData(params, requestId);
        String timestamp = LocalDateTime.now().format(
                DateTimeFormatter.ofPattern("yyyyMMddHHmmss"));
        String filename = URLEncoder.encode(
                (ebay ? "eBay" : "AMZ") + "-SOP售后数据-" + startDate + "-" + endDate
                        + "-" + timestamp + ".xlsx",
                StandardCharsets.UTF_8).replace("+", "%20");
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename*=UTF-8''" + filename)
                .contentType(MediaType.parseMediaType(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                .contentLength(file.length)
                .body(file);
    }

    @Log(title = "eBay-SOP销量文件导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('sop:afterSales:import')")
    @PostMapping("/ebay-sales-import")
    public AjaxResult importEbaySales(
            @RequestParam("file") MultipartFile file,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey)
    {
        try
        {
            return success(pythonClient.importEbaySopSales(
                    file, SecurityUtils.getUsername(), requestId, idempotencyKey).get("data"));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "eBay-SOP历史售后文件导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('sop:afterSales:import')")
    @PostMapping("/ebay-history-import")
    public AjaxResult importEbayHistory(
            @RequestParam("file") MultipartFile file,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey)
    {
        try
        {
            return success(pythonClient.importEbaySopHistory(
                    file, SecurityUtils.getUsername(), requestId, idempotencyKey).get("data"));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "eBay-SOP售后文件导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('sop:afterSales:import')")
    @PostMapping("/ebay-after-sales-import")
    public AjaxResult importEbayAfterSales(
            @RequestParam("file") MultipartFile file,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey)
    {
        try
        {
            return success(pythonClient.importEbaySopAfterSales(
                    file, SecurityUtils.getUsername(), requestId, idempotencyKey).get("data"));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    private boolean isEbay(String platform)
    {
        return "ebay".equalsIgnoreCase(platform);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value)
    {
        return value instanceof Map<?, ?>
                ? (Map<String, Object>) value : Map.of();
    }
}
