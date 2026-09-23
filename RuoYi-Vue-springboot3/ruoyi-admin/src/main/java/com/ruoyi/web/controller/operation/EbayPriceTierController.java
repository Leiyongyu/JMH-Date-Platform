package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

/** 首页价格分层：复用eBay查看权限，不提供原始表修改或接口拉取操作。 */
@RestController
@RequestMapping("/operations/ebay/price-tier")
public class EbayPriceTierController extends BaseController
{
    private final PerformancePythonClient pythonClient;

    public EbayPriceTierController(PerformancePythonClient pythonClient)
    {
        this.pythonClient = pythonClient;
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:list')")
    /** month 为空取最新统计月份，shop 为空返回全部店铺。 */
    @GetMapping("/summary")
    public AjaxResult summary(@RequestParam(value = "month", required = false) String month,
            @RequestParam(value = "shop", required = false) String shop,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(pythonClient.ebayPriceTierSummary(month, shop, requestId).get("data"));
    }

    /** 产品结构：各月各价格档的不良交易率，只读，不触发任何重算。 */
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:list')")
    @GetMapping("/product-structure")
    public AjaxResult productStructure(@RequestParam(value = "year", required = false) String year,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(pythonClient.ebayProductStructure(year, requestId).get("data"));
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:list')")
    @PostMapping("/refresh")
    public AjaxResult refresh(@RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(pythonClient.refreshEbayPriceTier(requestId).get("data"));
    }
}
