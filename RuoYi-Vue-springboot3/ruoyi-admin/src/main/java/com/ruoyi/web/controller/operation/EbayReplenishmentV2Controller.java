package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.domain.operation.ebay.EbayReplenishmentV2LeadTimeSaveRequest;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2LeadTimeService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import com.ruoyi.system.service.operation.ebay.EbayWarehouseRentService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2ExportService;
import jakarta.servlet.http.HttpServletResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 运营中心-eBay补货2.0。 */
@Tag(name = "运营中心-eBay补货2.0")
@RestController
@RequestMapping("/operations/ebay/replenishment-v2")
public class EbayReplenishmentV2Controller extends BaseController
{
    private static final int MAX_PAGE_SIZE = 200;

    private final EbayReplenishmentV2PythonClient client;
    private final EbayReplenishmentV2LeadTimeService leadTimeService;
    private final EbayWarehouseRentService warehouseRentService;
    private final EbayReplenishmentV2ExportService exportService;

    public EbayReplenishmentV2Controller(
            EbayReplenishmentV2PythonClient client,
            EbayReplenishmentV2LeadTimeService leadTimeService,
            EbayWarehouseRentService warehouseRentService,
            EbayReplenishmentV2ExportService exportService)
    {
        this.client = client;
        this.leadTimeService = leadTimeService;
        this.warehouseRentService = warehouseRentService;
        this.exportService = exportService;
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:list')")
    @GetMapping("/list")
    public AjaxResult list(
            @RequestParam(required = false) String site,
            @RequestParam(required = false) String sku,
            @RequestParam(required = false) String productLevel,
            @RequestParam(required = false) String productNature,
            @RequestParam(required = false) String salesType,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "50") int pageSize,
            @RequestParam(required = false) String sortField,
            @RequestParam(required = false) String sortOrder,
            @RequestHeader(value = "X-Request-ID", required = false)
                    String requestId)
    {
        Map<String, Object> params = queryParameters(
                site, sku, productLevel, productNature, salesType, sortField, sortOrder);
        params.put("page", Math.max(pageNum, 1));
        params.put("page_size", Math.min(
                Math.max(pageSize, 1), MAX_PAGE_SIZE));
        Object result = data(client.list(params, requestId));
        return success(enrich(result));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:list')")
    @Log(title = "eBay补货2.0导出", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(
            @RequestParam(required = false) String site,
            @RequestParam(required = false) String sku,
            @RequestParam(required = false) String productLevel,
            @RequestParam(required = false) String productNature,
            @RequestParam(required = false) String salesType,
            @RequestParam(required = false) String sortField,
            @RequestParam(required = false) String sortOrder,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            HttpServletResponse response)
    {
        Map<String, Object> params = queryParameters(
                site, sku, productLevel, productNature, salesType, sortField, sortOrder);
        Object result = enrich(data(client.exportData(params, requestId)));
        exportService.export(result, params, response);
    }

    private Map<String, Object> queryParameters(String site, String sku, String productLevel,
            String productNature, String salesType, String sortField, String sortOrder)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("site", trimToNull(site));
        params.put("sku", trimToNull(sku));
        params.put("product_level", trimToNull(productLevel));
        params.put("product_nature", trimToNull(productNature));
        params.put("sales_type", trimToNull(salesType));
        params.put("sort_field", trimToNull(sortField));
        params.put("sort_order", normalizeSortOrder(sortOrder));
        return params;
    }

    /** 列表和导出复用同一补充逻辑；批量限制IN长度，不逐SKU查库。 */
    private Object enrich(Object result)
    {
        if (result instanceof Map<?, ?> dataMap && dataMap.get("items") instanceof List<?> items)
        {
            for (int start = 0; start < items.size(); start += MAX_PAGE_SIZE)
            {
                Map<String, Object> batch = new LinkedHashMap<>();
                batch.put("items", items.subList(start, Math.min(start + MAX_PAGE_SIZE, items.size())));
                leadTimeService.enrich(batch);
                warehouseRentService.enrich(batch);
            }
        }
        return result;
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:formula')")
    @GetMapping("/formula")
    public AjaxResult formula(
            @RequestHeader(value = "X-Request-ID", required = false)
                    String requestId)
    {
        return success(data(client.formula(requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:formula')")
    @Log(title = "eBay补货2.0公式配置", businessType = BusinessType.UPDATE)
    @PostMapping("/formula")
    public AjaxResult saveFormula(
            @RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false)
                    String requestId)
    {
        Map<String, Object> payload = new LinkedHashMap<>();
        if (body != null) payload.putAll(body);
        payload.put("operator", getUsername());
        return success(data(client.saveFormula(payload, requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:importWarehouseRent')")
    @Log(title = "eBay补货2.0仓租明细导入", businessType = BusinessType.IMPORT)
    @PostMapping("/warehouse-rent/import")
    public AjaxResult importWarehouseRent(
            @RequestParam("file") MultipartFile file)
    {
        return success(warehouseRentService.importFile(file, getUsername()));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:editLeadTime')")
    @Log(title = "eBay补货2.0人工时效", businessType = BusinessType.UPDATE)
    @PutMapping("/lead-time")
    public AjaxResult saveLeadTime(
            @RequestBody EbayReplenishmentV2LeadTimeSaveRequest request)
    {
        leadTimeService.save(request, getUsername());
        return success();
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:formula')")
    @GetMapping("/forecast-rule")
    public AjaxResult forecastRules(
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(data(client.forecastRules(requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:formula')")
    @Log(title = "eBay补货2.0预估销量2规则配置", businessType = BusinessType.UPDATE)
    @PostMapping("/forecast-rule")
    public AjaxResult saveForecastRules(
            @RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> payload = new LinkedHashMap<>(body);
        payload.put("operator", getUsername());
        return success(data(client.saveForecastRules(payload, requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:formula')")
    @PostMapping("/forecast-rule/validate")
    public AjaxResult validateForecastRules(
            @RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(data(client.validateForecastRules(body, requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:formula')")
    @PostMapping("/forecast-rule/preview")
    public AjaxResult previewForecastRules(
            @RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(data(client.previewForecastRules(body, requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:formula')")
    @GetMapping("/forecast-rule/sku")
    public AjaxResult forecastRuleSku(
            @RequestParam String site, @RequestParam String sku,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(data(client.forecastRuleSku(Map.of("site", site, "sku", sku), requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:formula')")
    @GetMapping("/level-rule")
    public AjaxResult levelRules(
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(data(client.levelRules(requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:formula')")
    @Log(title = "eBay补货2.0产品等级规则", businessType = BusinessType.UPDATE)
    @PostMapping("/level-rule")
    public AjaxResult saveLevelRules(@RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> payload = new LinkedHashMap<>(body);
        payload.put("operator", getUsername());
        return success(data(client.saveLevelRules(payload, requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:formula')")
    @PostMapping("/level-rule/validate")
    public AjaxResult validateLevelRules(@RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(data(client.validateLevelRules(body, requestId)));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:editSalesType')")
    @Log(title = "eBay补货2.0销售类型", businessType = BusinessType.UPDATE)
    @PostMapping("/sales-type")
    public AjaxResult saveSalesType(@RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String, Object> payload = new LinkedHashMap<>(body);
        payload.put("operator", getUsername());
        return success(data(client.saveSalesType(payload, requestId)));
    }

    private Object data(Map<String, Object> response)
    {
        return response.get("data");
    }

    private String trimToNull(String value)
    {
        return StringUtils.hasText(value) ? value.trim() : null;
    }

    private String normalizeSortOrder(String value)
    {
        if (!StringUtils.hasText(value)) return null;
        String normalized = value.trim();
        return "asc".equalsIgnoreCase(normalized)
                || "ascending".equalsIgnoreCase(normalized)
                ? "asc"
                : "desc";
    }
}
