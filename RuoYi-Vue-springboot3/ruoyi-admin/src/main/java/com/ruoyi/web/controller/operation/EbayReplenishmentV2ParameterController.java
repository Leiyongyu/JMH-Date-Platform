package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2ParameterService;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/operations/ebay/replenishment-v2/parameters")
public class EbayReplenishmentV2ParameterController extends BaseController
{
    private final EbayReplenishmentV2ParameterService service;

    public EbayReplenishmentV2ParameterController(EbayReplenishmentV2ParameterService service)
    {
        this.service = service;
    }

    @GetMapping
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:list')")
    public AjaxResult get()
    {
        return success(service.get());
    }

    @PutMapping
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:formula')")
    @Log(title = "eBay补货2.0参数", businessType = BusinessType.UPDATE)
    public AjaxResult save(@RequestBody EbayReplenishmentV2ParameterService.SaveRequest request)
    {
        return success(service.save(request, getUsername()));
    }
}
