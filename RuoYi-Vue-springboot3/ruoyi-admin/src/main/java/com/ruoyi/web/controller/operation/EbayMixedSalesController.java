package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/operations/mixed-sales/ebay")
public class EbayMixedSalesController extends BaseController
{
    private final EbayReplenishmentV2PythonClient client;
    public EbayMixedSalesController(EbayReplenishmentV2PythonClient client) { this.client = client; }

    @PreAuthorize("@ss.hasPermi('operations:mixedSales:list')")
    @GetMapping({"/list", "/details"})
    public AjaxResult list(
            @RequestParam(required = false) String site,
            @RequestParam(required = false) String sku,
            @RequestParam(required = false) String productName,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "50") int pageSize,
            @RequestParam(required = false) String sortField,
            @RequestParam(required = false) String sortOrder,
            @RequestParam(required = false) String calculationVersion,
            @RequestParam(required = false) String statMonth,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            jakarta.servlet.http.HttpServletRequest request)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("site", clean(site)); params.put("sku", clean(sku));
        params.put("product_name", clean(productName));
        params.put("page", Math.max(pageNum, 1));
        params.put("page_size", Math.min(Math.max(pageSize, 1), 200));
        params.put("sort_field", clean(sortField)); params.put("sort_order", clean(sortOrder));
        params.put("calculation_version", clean(calculationVersion));
        params.put("stat_month", clean(statMonth));
        params.put("age_operator", clean(request.getParameter("ageOperator")));
        params.put("age_days", clean(request.getParameter("ageDays")));
        Map<String, Object> response = client.mixedSales(params, request.getRequestURI().endsWith("/details"), requestId);
        return success(response.get("data"));
    }

    private String clean(String value) { return value == null || value.isBlank() ? null : value.trim(); }

    @PreAuthorize("@ss.hasPermi('operations:mixedSales:list')")
    @GetMapping("/prices")
    public AjaxResult prices(@RequestParam String sku,
            @RequestParam(required = false) String site,
            @RequestParam(required = false) String statMonth,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "20") int pageSize,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        Map<String,Object> params = new LinkedHashMap<>();
        params.put("sku", clean(sku)); params.put("site", clean(site)); params.put("stat_month", clean(statMonth));
        params.put("page", Math.max(pageNum,1)); params.put("page_size",Math.min(Math.max(pageSize,1),200));
        return success(client.mixedSalesPrices(params,requestId).get("data"));
    }
}
