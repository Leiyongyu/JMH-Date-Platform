package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

/** 首页销售看板。查询、上传分开授权，Python只接受内部服务请求。 */
@RestController
@RequestMapping("/finance/sales-dashboard")
public class SalesDashboardController extends BaseController
{
    private final PerformancePythonClient client;

    public SalesDashboardController(PerformancePythonClient client) { this.client = client; }

    @PreAuthorize("@ss.hasPermi('finance:salesDashboard:list')")
    @GetMapping("/options")
    public AjaxResult options(@RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.salesDashboardOptions(requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('finance:salesDashboard:list')")
    @GetMapping("/report")
    public AjaxResult report(@RequestParam String platform, @RequestParam String startMonth,
            @RequestParam String endMonth, @RequestParam(defaultValue = "") String groups,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try
        {
            return success(client.salesDashboardReport(Map.of("platform", platform,
                    "start_month", startMonth, "end_month", endMonth, "groups_csv", groups), requestId).get("data"));
        }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('finance:salesDashboard:list') and @ss.hasPermi('finance:salesDashboard:import')")
    @PostMapping("/preview")
    public AjaxResult preview(@RequestParam("file") MultipartFile file,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.previewSalesHistory(file, requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('finance:salesDashboard:list')")
    @GetMapping("/analysis")
    public AjaxResult analysis(@RequestParam String platform, @RequestParam String startMonth,
            @RequestParam String endMonth, @RequestParam(defaultValue = "") String groups,
            @RequestParam(defaultValue = "month") String granularity,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try
        {
            return success(client.salesDashboardReport(Map.of("platform", platform,
                    "start_month", startMonth, "end_month", endMonth, "groups_csv", groups,
                    "granularity", granularity), requestId).get("data"));
        }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "销售看板历史导入", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:salesDashboard:list') and @ss.hasPermi('finance:salesDashboard:import')")
    @PostMapping("/import")
    public AjaxResult importHistory(@RequestParam("file") MultipartFile file, @RequestParam String fileSha256,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.importSalesHistory(file, fileSha256, getUsername(), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }
}
