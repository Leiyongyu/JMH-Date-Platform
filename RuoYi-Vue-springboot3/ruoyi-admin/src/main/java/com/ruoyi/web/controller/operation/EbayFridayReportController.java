package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.operation.ebay.EbayFridayReportPythonClient;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

/**
 * 运营中心 / eBay / 数据报表 /「周五数据」：有货无货、海外仓库存两张表的每周快照。
 * 数据由每周五定时任务生成；ERP 只做鉴权、转发、店铺主站点维护与导出。
 */
@RestController
@RequestMapping("/operations/ebay/friday-report")
public class EbayFridayReportController extends BaseController
{
    private static final Pattern DATE = Pattern.compile("^20\\d{2}-\\d{2}-\\d{2}$");
    private static final Set<String> LISTING_KEYS = Set.of("reportDate", "keyword", "site", "storeName",
            "principalName", "flag", "sortField", "sortOrder", "pageNum", "pageSize");
    private static final Set<String> STOCK_KEYS = Set.of("reportDate", "keyword", "site", "brand",
            "principalName", "flag", "sortField", "sortOrder", "pageNum", "pageSize");
    private final EbayFridayReportPythonClient client;

    public EbayFridayReportController(EbayFridayReportPythonClient client)
    {
        this.client = client;
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayFridayReport:list')")
    @GetMapping("/overview")
    public AjaxResult overview(@RequestParam(required = false) String reportDate,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validDate(reportDate)) return error("报表日期格式不正确");
        try { return success(client.overview(query(Map.of("reportDate", nvl(reportDate)), Set.of("reportDate")), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayFridayReport:list')")
    @GetMapping("/listings")
    public AjaxResult listings(@RequestParam Map<String, String> params,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validDate(params.get("reportDate"))) return error("报表日期格式不正确");
        try { return success(client.listings(query(params, LISTING_KEYS), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayFridayReport:list')")
    @GetMapping("/stocks")
    public AjaxResult stocks(@RequestParam Map<String, String> params,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validDate(params.get("reportDate"))) return error("报表日期格式不正确");
        try { return success(client.stocks(query(params, STOCK_KEYS), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "eBay周五数据重新生成", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('operations:ebayFridayReport:edit')")
    @PostMapping("/generate")
    public AjaxResult generate(@RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.generate(Map.of("operator", nvl(operator())), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayFridayReport:list')")
    @GetMapping("/order-sales")
    public AjaxResult orderSales(@RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.orderSales(requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    /** 订单售出统计：上传数字酋长订单导出，整份替换上一份（沿用维护权限）。 */
    @Log(title = "eBay周五数据订单售出上传", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('operations:ebayFridayReport:edit')")
    @PostMapping("/order-sales/import")
    public AjaxResult importOrderSales(@RequestParam("file") MultipartFile file,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.importOrderSales(file, operator(), requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "eBay店铺主站点", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:ebayFridayReport:edit')")
    @PutMapping("/stores")
    public AjaxResult saveStore(@RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("store_name", body.get("storeName"));
        payload.put("original_key", body.get("originalKey"));
        payload.put("main_site", body.get("mainSite"));
        payload.put("second_site", body.get("secondSite"));
        payload.put("note", body.get("note"));
        payload.put("sort_order", body.get("sortOrder"));
        payload.put("operator", operator());
        try { return success(client.saveStore(payload, requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "eBay店铺主站点", businessType = BusinessType.DELETE)
    @PreAuthorize("@ss.hasPermi('operations:ebayFridayReport:edit')")
    @DeleteMapping("/stores/{storeKey}")
    public AjaxResult deleteStore(@PathVariable String storeKey,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        try { return success(client.deleteStore(storeKey, requestId).get("data")); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "eBay周五数据导出", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('operations:ebayFridayReport:list') and @ss.hasPermi('operations:ebayFridayReport:export')")
    @GetMapping("/export")
    public ResponseEntity<?> export(@RequestParam(required = false) String reportDate,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        if (!validDate(reportDate)) return badRequest("报表日期格式不正确");
        try
        {
            byte[] file = client.export(query(Map.of("reportDate", nvl(reportDate)), Set.of("reportDate")), requestId);
            String name = URLEncoder.encode("周五数据" + (reportDate == null || reportDate.isBlank() ? "" : "-" + reportDate.trim())
                    + ".xlsx", StandardCharsets.UTF_8).replace("+", "%20");
            return ResponseEntity.ok()
                    .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename*=UTF-8''" + name)
                    .contentType(MediaType.parseMediaType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                    .contentLength(file.length)
                    .body(file);
        }
        catch (RuntimeException e)
        {
            return badRequest(String.valueOf(e.getMessage()));
        }
    }

    /** 只转发白名单参数，并把前端的驼峰名换成 Python 的下划线名。 */
    static Map<String, String> query(Map<String, String> params, Set<String> allowed)
    {
        Map<String, String> result = new LinkedHashMap<>();
        params.forEach((key, value) -> {
            if (!allowed.contains(key) || value == null || value.isBlank()) return;
            String name = switch (key)
            {
                case "pageNum" -> "page";
                case "pageSize" -> "page_size";
                default -> key.replaceAll("([A-Z])", "_$1").toLowerCase();
            };
            result.put(name, value.trim());
        });
        return result;
    }

    protected String operator()
    {
        try { return getUsername(); }
        catch (RuntimeException e) { return null; }
    }

    private static String nvl(String value)
    {
        return value == null ? "" : value;
    }

    private static boolean validDate(String value)
    {
        return value == null || value.isBlank() || DATE.matcher(value.trim()).matches();
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
