package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import com.ruoyi.framework.web.service.PermissionService;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.security.access.AccessDeniedException;
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

/** 数据中心月度库存报表：代理Python明细、汇总、导出及同步接口。 */
@Tag(name = "数据中心-月度库存报表")
@RestController
@RequestMapping("/finance/monthly-inventory-report")
public class MonthlyInventoryReportController extends BaseController
{
    private final PerformancePythonClient pythonClient;
    private final PermissionService permissionService;
    public MonthlyInventoryReportController(PerformancePythonClient pythonClient,
            PermissionService permissionService)
    {
        this.pythonClient = pythonClient;
        this.permissionService = permissionService;
    }

    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:list')")
    @GetMapping("/months")
    public AjaxResult months(
            @RequestParam(defaultValue = "24") int limit,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return success(data(pythonClient.monthlyInventoryReportMonths(
                    limit, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:list') and @ss.hasPermi('finance:monthlyInventoryReport:viewGroup')")
    @GetMapping("/summary")
    public AjaxResult summary(
            @RequestParam(required = false) String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return success(data(pythonClient.monthlyInventoryReportSummary(
                    statMonth, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:list')")
    @GetMapping("/dimension-summary")
    public AjaxResult dimensionSummary(
            @RequestParam String dimensionType,
            @RequestParam(required = false) String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            requireDimensionPermission(dimensionType);
            return success(data(
                    pythonClient.monthlyInventoryReportDimensionSummary(
                            dimensionType, statMonth, requestId)));
        }
        catch (AccessDeniedException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "月度库存报表导出", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:list')")
    @GetMapping("/export")
    public ResponseEntity<byte[]> export(
            @RequestParam String statMonth,
            @RequestParam(defaultValue = "GROUP") String dimensionType,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            String allowedDimensions = exportDimensions(dimensionType);
            byte[] file = pythonClient.exportMonthlyInventoryReport(
                    statMonth, allowedDimensions, requestId);
            String reportMonth = YearMonth.parse(statMonth).plusMonths(1)
                    .toString();
            String dimensionLabel = switch (dimensionType.toUpperCase())
            {
                case "STORE" -> "店铺";
                case "OWNER" -> "负责人";
                case "ALL" -> "汇总";
                default -> "组别";
            };
            String timestamp = LocalDateTime.now().format(
                    DateTimeFormatter.ofPattern("yyyyMMddHHmmss"));
            String filename = URLEncoder.encode(
                    reportMonth + "-月度库存-" + dimensionLabel + "-"
                            + timestamp + ".xlsx",
                    StandardCharsets.UTF_8).replace("+", "%20");
            return ResponseEntity.ok()
                    .header(HttpHeaders.CONTENT_DISPOSITION,
                            "attachment; filename*=UTF-8''" + filename)
                    .contentType(MediaType.parseMediaType(
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                    .contentLength(file.length)
                    .body(file);
        }
        catch (AccessDeniedException e)
        {
            throw e;
        }
        catch (RuntimeException e)
        {
            byte[] message = String.valueOf(e.getMessage()).getBytes(
                    StandardCharsets.UTF_8);
            return ResponseEntity.badRequest()
                    .contentType(new MediaType("text", "plain", StandardCharsets.UTF_8))
                    .contentLength(message.length)
                    .body(message);
        }
    }

    private void requireDimensionPermission(String dimensionType)
    {
        String dimension = String.valueOf(dimensionType).toUpperCase(Locale.ROOT);
        String permission = switch (dimension)
        {
            case "GROUP" -> "finance:monthlyInventoryReport:viewGroup";
            case "STORE" -> "finance:monthlyInventoryReport:viewStore";
            case "OWNER" -> "finance:monthlyInventoryReport:viewOwner";
            default -> throw new IllegalArgumentException("月度库存维度无效");
        };
        if (!permissionService.hasPermi(permission))
        {
            throw new AccessDeniedException("没有查看该月度库存维度的权限");
        }
    }

    private String exportDimensions(String requestedDimension)
    {
        String requested = String.valueOf(requestedDimension).toUpperCase(Locale.ROOT);
        if (!"ALL".equals(requested))
        {
            requireDimensionPermission(requested);
            return requested;
        }
        List<String> allowed = List.of("GROUP", "STORE", "OWNER").stream()
                .filter(dimension -> permissionService.hasPermi(switch (dimension)
                {
                    case "GROUP" -> "finance:monthlyInventoryReport:viewGroup";
                    case "STORE" -> "finance:monthlyInventoryReport:viewStore";
                    default -> "finance:monthlyInventoryReport:viewOwner";
                }))
                .toList();
        if (allowed.isEmpty())
        {
            throw new AccessDeniedException("没有可导出的月度库存维度权限");
        }
        return "VISIBLE:" + String.join(",", allowed);
    }
    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:list') and @ss.hasPermi('finance:monthlyInventoryReport:viewGroup')")
    @GetMapping("/list")
    public AjaxResult list(
            @RequestParam String sourceType,
            @RequestParam(required = false) String statMonth,
            @RequestParam(required = false) String departmentCode,
            @RequestParam(required = false) String principalName,
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "50") int pageSize,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            Map<String, Object> params = new LinkedHashMap<>();
            params.put("source_type", sourceType);
            params.put("stat_month", statMonth);
            params.put("department_code", departmentCode);
            params.put("principal_name", principalName);
            params.put("keyword", keyword);
            params.put("page", pageNum);
            params.put("page_size", pageSize);
            return detailTable(pythonClient.monthlyInventoryReportDetails(
                    params, requestId));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "月度库存报表重新清洗", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:edit')")
    @PostMapping("/rebuild")
    public AjaxResult rebuild(
            @RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return success(data(pythonClient.rebuildMonthlyInventoryReport(
                    statMonth, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "月度库存Amazon订单利润拉取", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:edit')")
    @PostMapping("/order-profit-sync")
    public AjaxResult syncOrderProfit(
            @RequestParam(required = false) String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId)
    {
        try
        {
            return success(data(
                    pythonClient.syncMonthlyInventoryOrderProfit(
                            statMonth, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "月度库存采购单在途导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:edit')")
    @PostMapping("/purchase-order-import")
    public AjaxResult importPurchaseOrder(
            @RequestParam String statMonth,
            @RequestParam("file") MultipartFile file,
            @RequestHeader(value = "X-Request-ID", required = false)
            String requestId,
            @RequestHeader(value = "Idempotency-Key", required = false)
            String idempotencyKey)
    {
        try
        {
            return success(data(
                    pythonClient.importMonthlyInventoryPurchaseOrder(
                            statMonth,
                            file,
                            getUsername(),
                            requestId,
                            idempotencyKey)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:edit') and @ss.hasPermi('finance:monthlyInventoryReport:viewGroup')")
    @PostMapping("/history-preview")
    public AjaxResult previewHistory(
            @RequestParam("file") MultipartFile file,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        requireAdminRole();
        try
        {
            return success(data(pythonClient.previewMonthlyInventoryHistory(file, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @Log(title = "月度库存组别历史补录", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:edit') and @ss.hasPermi('finance:monthlyInventoryReport:viewGroup')")
    @PostMapping("/history-import")
    public AjaxResult importHistory(
            @RequestParam("file") MultipartFile file,
            @RequestParam String fileSha256,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        requireAdminRole();
        try
        {
            return success(data(pythonClient.importMonthlyInventoryHistory(
                    file, fileSha256, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    private void requireAdminRole()
    {
        if (!SecurityUtils.isAdmin() && !permissionService.hasRole("admin"))
        {
            throw new AccessDeniedException("只有系统管理员角色可以补录月度库存组别历史数据");
        }
    }

    private Object data(Map<String, Object> response)
    {
        return response.get("data");
    }

    @SuppressWarnings("unchecked")
    private AjaxResult detailTable(Map<String, Object> response)
    {
        Object value = response.get("data");
        Map<String, Object> data = value instanceof Map<?, ?>
                ? (Map<String, Object>) value : Map.of();
        Object pageValue = data.get("pagination");
        Map<String, Object> pagination = pageValue instanceof Map<?, ?>
                ? (Map<String, Object>) pageValue : Map.of();
        Object items = data.get("items");
        return AjaxResult.success()
                .put("rows", items instanceof List<?> ? items : List.of())
                .put("total", pagination.getOrDefault("total", 0))
                .put("statMonth", data.get("stat_month"))
                .put("sourceType", data.get("source_type"))
                .put("requestId", response.get("request_id"));
    }
}
