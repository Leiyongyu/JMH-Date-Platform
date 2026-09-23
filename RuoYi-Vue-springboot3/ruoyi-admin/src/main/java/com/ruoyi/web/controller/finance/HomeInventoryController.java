package com.ruoyi.web.controller.finance;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/finance/home-inventory")
public class HomeInventoryController extends BaseController
{
    private static final String INVENTORY = "@ss.hasPermi('finance:monthlyInventoryReport:list') and @ss.hasPermi('finance:slowMovingClearance:list')";
    private static final String SKU = "@ss.hasPermi('operations:amzReplenishment:list') and @ss.hasPermi('operations:ebayReplenishmentV2:list')";
    private final PerformancePythonClient client;
    public HomeInventoryController(PerformancePythonClient client) { this.client = client; }

    @PreAuthorize(INVENTORY)
    @GetMapping("/summary")
    public AjaxResult summary(@RequestParam(required=false) String month,
            @RequestHeader(value="X-Request-ID",required=false) String requestId)
    {
        return success(client.homeInventorySummary(month, requestId).get("data"));
    }

    @PreAuthorize(INVENTORY + " and " + SKU)
    @GetMapping("/sku")
    public AjaxResult sku(@RequestParam String month,
            @RequestHeader(value="X-Request-ID",required=false) String requestId)
    {
        return success(client.homeInventorySku(month, requestId).get("data"));
    }

    @PreAuthorize(INVENTORY + " and " + SKU)
    @PostMapping("/sku-snapshot")
    public AjaxResult snapshot(@RequestHeader(value="X-Request-ID",required=false) String requestId)
    {
        return success(client.captureHomeInventorySku(requestId).get("data"));
    }
}
