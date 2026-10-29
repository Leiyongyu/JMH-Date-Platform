package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.domain.operation.AmzMixedSalesQuery;
import com.ruoyi.system.service.operation.AmzMixedSalesService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import java.util.LinkedHashMap;
import java.util.Map;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "运营中心-混销")
@RestController
@RequestMapping("/operations/mixed-sales/amz")
public class AmzMixedSalesController extends BaseController
{
    private final AmzMixedSalesService service;
    private final EbayReplenishmentV2PythonClient client;
    public AmzMixedSalesController(AmzMixedSalesService service, EbayReplenishmentV2PythonClient client)
    { this.service = service; this.client = client; }

    @PreAuthorize("@ss.hasPermi('operations:mixedSales:list')")
    @GetMapping("/list")
    public AjaxResult list(AmzMixedSalesQuery query) { return query(query, false); }

    @PreAuthorize("@ss.hasPermi('operations:mixedSales:list')")
    @GetMapping("/details")
    public AjaxResult details(AmzMixedSalesQuery query) { return query(query, true); }

    private AjaxResult query(AmzMixedSalesQuery q, boolean details)
    {
        Map<String,Object> params = new LinkedHashMap<>();
        params.put("platform", "amz"); params.put("sku", q.getSku());
        params.put("product_name", q.getProductName()); params.put("sid", q.getSid());
        params.put("page", Math.max(q.getPageNum(), 1));
        params.put("page_size", Math.min(Math.max(q.getPageSize(), 1), 200));
        params.put("sort_field", q.getSortField()); params.put("sort_order", q.getSortOrder());
        params.put("calculation_version", q.getCalculationVersion());
        params.put("stat_month", q.getStatMonth());
        params.put("age_bucket", q.getAgeBucket());
        return success(client.mixedSales(params, details, null).get("data"));
    }

    @PreAuthorize("@ss.hasPermi('operations:mixedSales:list')")
    @GetMapping("/stores")
    public AjaxResult stores() { return success(service.stores()); }
}
