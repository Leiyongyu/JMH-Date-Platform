package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 财务中心绩效排名，统一代理 Python 绩效服务。 */
@Tag(name = "财务-绩效排名")
@RestController
@RequestMapping("/finance/performance-ranking")
public class PerformanceRankingController extends BaseController
{
    private final PerformancePythonClient pythonClient;

    public PerformanceRankingController(
            PerformancePythonClient pythonClient)
    {
        this.pythonClient = pythonClient;
    }

    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:list')")
    @GetMapping("/months")
    public AjaxResult months(
            @RequestParam(defaultValue = "12") int limit,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return success(data(pythonClient.months(limit, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:list')")
    @GetMapping("/list")
    public AjaxResult list(
            @RequestParam(defaultValue = "combined") String platform,
            @RequestParam(required = false) String statMonth,
            @RequestParam(required = false) String principalName,
            @RequestParam(defaultValue = "gross_profit") String orderBy,
            @RequestParam(defaultValue = "desc") String order,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "100") int pageSize,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            Map<String, Object> params = new LinkedHashMap<>();
            params.put("platform", platform);
            params.put("stat_month", statMonth);
            params.put("principal_name", principalName);
            params.put("order_by", orderBy);
            params.put("order", order);
            params.put("page", pageNum);
            params.put("page_size", pageSize);
            return rankingTable(pythonClient.rankings(params, requestId));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "绩效排名刷新", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:edit')")
    @PostMapping("/refresh")
    public AjaxResult refresh(
            @RequestParam String statMonth,
            @RequestParam(defaultValue = "combined") String platform,
            @RequestParam(defaultValue = "false")
            boolean requireAllPlatforms,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return success(data(pythonClient.refresh(
                    statMonth, platform, requireAllPlatforms, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "AMZ绩效源数据导出", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:list')")
    @GetMapping("/amazon/source-export")
    public ResponseEntity<byte[]> exportAmazonSource(
            @RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        byte[] file = pythonClient.exportAmazonPerformanceSource(
                statMonth, requestId);
        String filename = URLEncoder.encode(
                "amz_performance_source_" + statMonth + ".xlsx",
                StandardCharsets.UTF_8).replace("+", "%20");
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename*=UTF-8''" + filename)
                .contentType(MediaType.parseMediaType(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                .contentLength(file.length)
                .body(file);
    }

    @Log(title = "AMZ与eBay月度绩效负责人规则导入",
            businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:edit')")
    @PostMapping("/owner-rules/import")
    public AjaxResult importOwnerRules(
            @RequestParam("file") MultipartFile file,
            @RequestParam(defaultValue = "true") boolean rebuild,
            @RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId,
            @RequestHeader(value = "Idempotency-Key", required = false)
            String idempotencyKey)
    {
        try
        {
            return success(data(pythonClient.importUnifiedOwnerRules(
                    file, rebuild, statMonth, getUsername(),
                    requestId, idempotencyKey)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:list')")
    @GetMapping("/owner-rules/summary")
    public AjaxResult ownerRuleSummary(
            @RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return success(data(pythonClient.ownerRuleSummary(
                    "amazon", statMonth, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:list')")
    @GetMapping("/ebay/list")
    public AjaxResult ebayList(
            @RequestParam(required = false) String statMonth,
            @RequestParam(required = false) String principalName,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "100") int pageSize,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            Map<String, Object> params = new LinkedHashMap<>();
            params.put("platform", "ebay");
            params.put("stat_month", statMonth);
            params.put("principal_name", principalName);
            params.put("page", pageNum);
            params.put("page_size", pageSize);
            return rankingTable(pythonClient.rankings(params, requestId));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "eBay绩效排名刷新",
            businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:edit')")
    @PostMapping("/ebay/refresh")
    public AjaxResult refreshEbay(
            @RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return success(data(pythonClient.refresh(
                    statMonth, "ebay", false, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "eBay月度绩效利润导入",
            businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:edit')")
    @PostMapping("/ebay/profit/import")
    public AjaxResult importEbayProfit(
            @RequestParam("file") MultipartFile file,
            @RequestParam(defaultValue = "true") boolean rebuild,
            @RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId,
            @RequestHeader(value = "Idempotency-Key", required = false)
            String idempotencyKey)
    {
        try
        {
            return success(data(pythonClient.importEbayProfit(
                    file, rebuild, statMonth, getUsername(),
                    requestId, idempotencyKey)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:performanceRanking:list')")
    @GetMapping("/ebay/owner-rules/summary")
    public AjaxResult ebayOwnerRuleSummary(
            @RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return success(data(pythonClient.ownerRuleSummary(
                    "ebay", statMonth, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @SuppressWarnings("unchecked")
    private Object data(Map<String, Object> response)
    {
        return response.get("data");
    }

    @SuppressWarnings("unchecked")
    private AjaxResult rankingTable(Map<String, Object> response)
    {
        Object value = response.get("data");
        Map<String, Object> data = value instanceof Map<?, ?>
                ? (Map<String, Object>) value
                : Map.of();
        Object paginationValue = data.get("pagination");
        Map<String, Object> pagination = paginationValue instanceof Map<?, ?>
                ? (Map<String, Object>) paginationValue
                : Map.of();
        Object items = data.get("items");

        return AjaxResult.success()
                .put("rows", items instanceof List<?> ? items : List.of())
                .put("total", pagination.getOrDefault("total", 0))
                .put("statMonth", data.get("stat_month"))
                .put("platform", data.get("platform"))
                .put("currency", data.get("currency"))
                .put("partial", data.get("partial"))
                .put("requestId", response.get("request_id"));
    }
}
