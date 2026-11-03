package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

/** AMZ利润报表（店铺/个人维度，USD）。数据由Python按月拉取，ERP只负责鉴权与转发。 */
@RestController
@RequestMapping("/finance/amz-profit-report")
public class AmzProfitReportController extends BaseController
{
    private final PerformancePythonClient client;

    public AmzProfitReportController(PerformancePythonClient client) { this.client = client; }

    @PreAuthorize("@ss.hasPermi('finance:amzProfitReport:list')")
    @GetMapping("/months")
    public AjaxResult months(@RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.amzProfitReportMonths(requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('finance:amzProfitReport:list')")
    @GetMapping("/report")
    public AjaxResult report(@RequestParam String statMonth,
            @RequestParam(defaultValue = "STORE") String dimension,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.amzProfitReport(statMonth, dimension, requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "AMZ利润报表导出", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('finance:amzProfitReport:list') and @ss.hasPermi('finance:amzProfitReport:export')")
    @GetMapping("/export")
    public ResponseEntity<?> export(@RequestParam String startMonth, @RequestParam String endMonth,
            @RequestParam(defaultValue = "STORE,OWNER") String dimensions,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try
        {
            byte[] file = client.exportAmzProfitReport(startMonth, endMonth, dimensions, requestId);
            String filename = URLEncoder.encode("AMZ利润报表-" + startMonth + "至" + endMonth + ".xlsx",
                    StandardCharsets.UTF_8).replace("+", "%20");
            return ResponseEntity.ok()
                    .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename*=UTF-8''" + filename)
                    .contentType(MediaType.parseMediaType(
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                    .contentLength(file.length)
                    .body(file);
        }
        catch (RuntimeException e)
        {
            byte[] message = String.valueOf(e.getMessage()).getBytes(StandardCharsets.UTF_8);
            return ResponseEntity.badRequest()
                    .contentType(new MediaType("text", "plain", StandardCharsets.UTF_8))
                    .contentLength(message.length)
                    .body(message);
        }
    }
}
