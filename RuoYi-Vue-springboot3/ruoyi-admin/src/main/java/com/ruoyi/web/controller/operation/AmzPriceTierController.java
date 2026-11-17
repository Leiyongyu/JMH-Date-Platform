package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

/** AMZ人民币五档；查看和重新统计均校验AMZ查看权限。 */
@RestController
@RequestMapping("/operations/amz/price-tier")
public class AmzPriceTierController extends BaseController
{
    private final PerformancePythonClient pythonClient;
    public AmzPriceTierController(PerformancePythonClient pythonClient) { this.pythonClient = pythonClient; }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/summary")
    public AjaxResult summary(@RequestHeader(value="X-Request-ID",required=false) String requestId)
    {
        return success(pythonClient.amzPriceTierSummary(requestId).get("data"));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/refresh")
    public AjaxResult refresh(@RequestHeader(value="X-Request-ID",required=false) String requestId)
    {
        return success(pythonClient.refreshAmzPriceTier(requestId).get("data"));
    }
}
