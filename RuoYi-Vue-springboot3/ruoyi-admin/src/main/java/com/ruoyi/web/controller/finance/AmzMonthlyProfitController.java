package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.finance.AmzMonthlyProfitPythonClient;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

/**
 * 财务中心「AMZ月度利润表」：店铺利润、小组利润（人民币，结算口径）。
 * 数据由 Python 每月定时从领星利润报表拉取；ERP 只做鉴权、补充费用维护的转发与导出。
 */
@RestController
@RequestMapping("/finance/amz-monthly-profit")
public class AmzMonthlyProfitController extends BaseController
{
    private static final Pattern MONTH = Pattern.compile("^20\\d{2}-(0[1-9]|1[0-2])$");
    private final AmzMonthlyProfitPythonClient client;

    public AmzMonthlyProfitController(AmzMonthlyProfitPythonClient client)
    {
        this.client = client;
    }

    @PreAuthorize("@ss.hasPermi('finance:amzMonthlyProfit:list')")
    @GetMapping("/months")
    public AjaxResult months(@RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.months(requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('finance:amzMonthlyProfit:list')")
    @GetMapping("/report")
    public AjaxResult report(@RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validMonth(statMonth)) return error("请选择正确的月份");
        try { return success(client.report(statMonth.trim(), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('finance:amzMonthlyProfit:list')")
    @GetMapping("/adjustments")
    public AjaxResult adjustments(@RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validMonth(statMonth)) return error("请选择正确的月份");
        try { return success(client.adjustments(statMonth.trim(), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "AMZ月度利润表补充费用", businessType = BusinessType.INSERT)
    @PreAuthorize("@ss.hasPermi('finance:amzMonthlyProfit:edit')")
    @PostMapping("/adjustments")
    public AjaxResult createAdjustment(@RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validMonth(String.valueOf(body.get("statMonth")))) return error("请选择正确的月份");
        try { return success(client.createAdjustment(payload(body, true), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "AMZ月度利润表补充费用", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('finance:amzMonthlyProfit:edit')")
    @PutMapping("/adjustments/{id}")
    public AjaxResult updateAdjustment(@PathVariable long id, @RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.updateAdjustment(id, payload(body, false), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "AMZ月度利润表补充费用", businessType = BusinessType.DELETE)
    @PreAuthorize("@ss.hasPermi('finance:amzMonthlyProfit:edit')")
    @DeleteMapping("/adjustments/{id}")
    public AjaxResult deleteAdjustment(@PathVariable long id,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.deleteAdjustment(id, requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "AMZ月度利润表导出", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('finance:amzMonthlyProfit:list') and @ss.hasPermi('finance:amzMonthlyProfit:export')")
    @GetMapping("/export")
    public ResponseEntity<?> export(@RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validMonth(statMonth)) return badRequest("请选择正确的月份");
        try
        {
            byte[] file = client.export(statMonth.trim(), requestId);
            String filename = URLEncoder.encode("AMZ月度利润表-" + statMonth.trim() + ".xlsx", StandardCharsets.UTF_8)
                    .replace("+", "%20");
            return ResponseEntity.ok()
                    .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename*=UTF-8''" + filename)
                    .contentType(MediaType.parseMediaType(
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                    .contentLength(file.length)
                    .body(file);
        }
        catch (RuntimeException e)
        {
            return badRequest(String.valueOf(e.getMessage()));
        }
    }

    /** 只转发约定字段，操作人取当前登录用户，不信任前端传入。 */
    private Map<String, Object> payload(Map<String, Object> body, boolean withMonth)
    {
        Map<String, Object> result = new LinkedHashMap<>();
        if (withMonth) result.put("stat_month", String.valueOf(body.get("statMonth")).trim());
        result.put("row_code", body.get("rowCode"));
        result.put("fee_item", body.get("feeItem"));
        result.put("amount", body.get("amount"));
        result.put("remark", body.get("remark"));
        result.put("operator", operator());
        return result;
    }

    protected String operator()
    {
        try { return getUsername(); }
        catch (RuntimeException e) { return null; }
    }

    private static boolean validMonth(String value)
    {
        return value != null && MONTH.matcher(value.trim()).matches();
    }

    private static ResponseEntity<byte[]> badRequest(String message)
    {
        byte[] body = message.getBytes(StandardCharsets.UTF_8);
        return ResponseEntity.badRequest()
                .contentType(new MediaType("text", "plain", StandardCharsets.UTF_8))
                .contentLength(body.length)
                .body(body);
    }
}
