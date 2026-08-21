package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 财务中心滞销清货，统一代理 Python 数据服务。 */
@Tag(name = "财务-滞销清货")
@RestController
@RequestMapping("/finance/slow-moving-clearance")
public class SlowMovingClearanceController extends BaseController
{
    private final PerformancePythonClient pythonClient;

    public SlowMovingClearanceController(
            PerformancePythonClient pythonClient)
    {
        this.pythonClient = pythonClient;
    }

    @PreAuthorize("@ss.hasPermi('finance:slowMovingClearance:list')")
    @GetMapping("/list")
    public AjaxResult list(
            @RequestParam(required = false) String pullMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return clearanceTable(
                    pythonClient.clearanceGroups(pullMonth, requestId));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:slowMovingClearance:list')")
    @GetMapping("/summary")
    public AjaxResult summary(
            @RequestParam(required = false) String pullMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return success(data(
                    pythonClient.clearanceSummary(pullMonth, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:slowMovingClearance:list')")
    @GetMapping("/months")
    public AjaxResult months(
            @RequestParam(defaultValue = "24") int limit,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return success(data(
                    pythonClient.clearanceMonths(limit, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "滞销清货库龄成本明细导出",
            businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('finance:slowMovingClearance:list')")
    @GetMapping("/inventory-age-cost/export")
    public ResponseEntity<byte[]> exportInventoryAgeDetails(
            @RequestParam String pullMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        byte[] file = pythonClient.exportInventoryAgeDetails(
                pullMonth, requestId);
        String timestamp = java.time.LocalDateTime.now().format(
                java.time.format.DateTimeFormatter.ofPattern(
                        "yyyyMMddHHmmss"));
        String filename = URLEncoder.encode(
                pullMonth + "-库龄明细-" + timestamp + ".xlsx",
                StandardCharsets.UTF_8).replace("+", "%20");
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename*=UTF-8''" + filename)
                .contentType(MediaType.parseMediaType(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                .contentLength(file.length)
                .body(file);
    }

    private Object data(Map<String, Object> response)
    {
        return response.get("data");
    }

    @SuppressWarnings("unchecked")
    private AjaxResult clearanceTable(Map<String, Object> response)
    {
        Object value = response.get("data");
        Map<String, Object> data = value instanceof Map<?, ?>
                ? (Map<String, Object>) value
                : Map.of();
        Object items = data.get("items");
        return AjaxResult.success()
                .put("rows", items instanceof List<?> ? items : List.of())
                .put("total", data.getOrDefault("total", 0))
                .put("pullMonth", data.get("pull_month"))
                .put("requestId", response.get("request_id"));
    }
}
