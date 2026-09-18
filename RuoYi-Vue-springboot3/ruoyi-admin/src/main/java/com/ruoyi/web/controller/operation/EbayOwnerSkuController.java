package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 首页 eBay 在售 SKU 统计，独立校验 eBay 补货2.0查看权限。 */
@RestController
@RequestMapping("/operations/ebay/owner-sku")
public class EbayOwnerSkuController extends BaseController
{
    private final PerformancePythonClient pythonClient;

    public EbayOwnerSkuController(PerformancePythonClient pythonClient)
    {
        this.pythonClient = pythonClient;
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:list')")
    @GetMapping("/summary")
    public AjaxResult summary(@RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(pythonClient.ebayOwnerSkuSummary(requestId).get("data"));
    }
}
