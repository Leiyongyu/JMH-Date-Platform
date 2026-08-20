package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 数据中心月度库存报表，统一代理Python清洗汇总服务。 */
@Tag(name = "数据中心-月度库存报表")
@RestController
@RequestMapping("/finance/monthly-inventory-report")
public class MonthlyInventoryReportController extends BaseController
{
    private final PerformancePythonClient pythonClient;

    public MonthlyInventoryReportController(
            PerformancePythonClient pythonClient)
    {
        this.pythonClient = pythonClient;
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

    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:list')")
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
            return success(data(
                    pythonClient.monthlyInventoryReportDimensionSummary(
                            dimensionType, statMonth, requestId)));
        }
        catch (Exception e)
        {
            return error(e.getMessage());
        }
    }

    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:list')")
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

    @Log(title = "月度库存eBay实际达成导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:monthlyInventoryReport:edit')")
    @PostMapping("/ebay-sales-import")
    public AjaxResult importEbaySales(
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
                    pythonClient.importMonthlyInventoryEbaySales(
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
