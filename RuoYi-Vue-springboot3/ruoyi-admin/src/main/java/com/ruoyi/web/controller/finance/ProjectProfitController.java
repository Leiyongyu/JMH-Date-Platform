package com.ruoyi.web.controller.finance;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.finance.ProjectProfitPythonClient;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

/**
 * 财务中心「项目利润总表」：小组项目利润表（eBay / EU / US1 / US2 / US3）与店铺维度利润表。
 * AMZ 由 Python 按领星利润报表现算；eBay 列上传财务 eBay 利润明细表；人力、分摊等手工录入。
 * ERP 只做鉴权与转发。
 */
@RestController
@RequestMapping("/finance/project-profit")
public class ProjectProfitController extends BaseController
{
    private static final Pattern MONTH = Pattern.compile("^20\\d{2}-(0[1-9]|1[0-2])$");
    private static final int MAX_ITEMS = 500;
    private final ProjectProfitPythonClient client;

    public ProjectProfitController(ProjectProfitPythonClient client)
    {
        this.client = client;
    }

    @PreAuthorize("@ss.hasPermi('finance:projectProfit:list')")
    @GetMapping("/months")
    public AjaxResult months(@RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.months(requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('finance:projectProfit:list')")
    @GetMapping("/report")
    public AjaxResult report(@RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validMonth(statMonth)) return error("请选择正确的月份");
        try { return success(client.report(statMonth.trim(), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    /** 手工项批量保存：只转发约定字段，操作人取当前登录用户。 */
    @Log(title = "项目利润总表手工项", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('finance:projectProfit:edit')")
    @PutMapping("/items")
    public AjaxResult saveItems(@RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        String month = String.valueOf(body.get("statMonth"));
        if (!validMonth(month)) return error("请选择正确的月份");
        if (!(body.get("items") instanceof List<?> raw) || raw.isEmpty()) return error("没有要保存的项目");
        if (raw.size() > MAX_ITEMS) return error("一次最多保存" + MAX_ITEMS + "项");
        List<Map<String, Object>> items = new ArrayList<>();
        for (Object entry : raw)
        {
            if (!(entry instanceof Map<?, ?> map)) return error("项目格式不正确");
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("group_code", map.get("groupCode"));
            item.put("item_code", map.get("itemCode"));
            item.put("amount", map.get("amount"));
            items.add(item);
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("stat_month", month.trim());
        payload.put("items", items);
        payload.put("operator", operator());
        try { return success(client.saveItems(payload, requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "项目利润总表eBay上传", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:projectProfit:edit')")
    @PostMapping("/ebay/import")
    public AjaxResult importEbay(@RequestParam("file") MultipartFile file, @RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validMonth(statMonth)) return error("请选择正确的月份");
        try { return success(client.importEbay(file, statMonth.trim(), operator(), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "项目利润总表领星利润报表上传", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('finance:projectProfit:edit')")
    @PostMapping("/amz/import")
    public AjaxResult importAmz(@RequestParam("file") MultipartFile file, @RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validMonth(statMonth)) return error("请选择正确的月份");
        try { return success(client.importAmz(file, statMonth.trim(), operator(), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "项目利润总表导出", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('finance:projectProfit:list') and @ss.hasPermi('finance:projectProfit:export')")
    @GetMapping("/export")
    public ResponseEntity<?> export(@RequestParam String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validMonth(statMonth)) return badRequest("请选择正确的月份");
        try
        {
            byte[] file = client.export(statMonth.trim(), requestId);
            String filename = URLEncoder.encode("项目利润总表-" + statMonth.trim() + ".xlsx", StandardCharsets.UTF_8)
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
