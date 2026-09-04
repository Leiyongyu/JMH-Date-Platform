package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.domain.operation.ebay.EbayReplenishmentV2LeadTimeSaveRequest;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2LeadTimeService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import com.ruoyi.system.service.operation.ebay.EbayWarehouseRentService;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.LinkedHashMap;
import java.util.Map;
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

    public EbayReplenishmentV2Controller(
            EbayReplenishmentV2PythonClient client,
            EbayReplenishmentV2LeadTimeService leadTimeService,
            EbayWarehouseRentService warehouseRentService)
    {
        this.client = client;
        this.leadTimeService = leadTimeService;
        this.warehouseRentService = warehouseRentService;
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:list')")
    @GetMapping("/list")
    public AjaxResult list(
            @RequestParam(required = false) String site,
            @RequestParam(required = false) String sku,
            @RequestParam(required = false) String productLevel,
            @RequestParam(required = false) String productNature,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "50") int pageSize,
            @RequestParam(required = false) String sortField,
            @RequestParam(required = false) String sortOrder,
            @RequestHeader(value = "X-Request-ID", required = false)
                    String requestId)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("site", trimToNull(site));
        params.put("sku", trimToNull(sku));
        params.put("product_level", trimToNull(productLevel));
        params.put("product_nature", trimToNull(productNature));
        params.put("page", Math.max(pageNum, 1));
        params.put("page_size", Math.min(
                Math.max(pageSize, 1), MAX_PAGE_SIZE));
        params.put("sort_field", trimToNull(sortField));
        params.put("sort_order", normalizeSortOrder(sortOrder));
        Object result = data(client.list(params, requestId));
        result = leadTimeService.enrich(result);
        return success(warehouseRentService.enrich(result));
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
