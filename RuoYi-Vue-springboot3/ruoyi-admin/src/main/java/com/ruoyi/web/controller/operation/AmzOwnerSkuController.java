package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import java.util.Map;

/** 首页 AMZ 在售 SKU 统计，复用 AMZ 补货查看权限。 */
@RestController
@RequestMapping("/operations/amz/owner-sku")
public class AmzOwnerSkuController extends BaseController
{
    private final PerformancePythonClient pythonClient;

    public AmzOwnerSkuController(PerformancePythonClient pythonClient)
    {
        this.pythonClient = pythonClient;
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/summary")
    public AjaxResult summary(@RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(pythonClient.amzOwnerSkuSummary(requestId).get("data"));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/nature/{view:summary|groups|owners|details|history|compare}")
    public AjaxResult nature(@PathVariable String view, @RequestParam Map<String, String> params,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId)
    {
        return success(pythonClient.productNature("amz", view, params, requestId).get("data"));
    }
}
