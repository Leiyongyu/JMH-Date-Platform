package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.domain.procurement.PendingPurchaseSubmitRequest;
import com.ruoyi.system.service.procurement.PendingPurchaseService;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 补货2.0操作列采购入口：使用独立权限，复用待采购业务，不授予采购中心其他权限。 */
@RestController
@RequestMapping("/operations/ebay/replenishment-v2/purchase")
public class EbayReplenishmentV2PurchaseController extends BaseController
{
    private final PendingPurchaseService service;

    public EbayReplenishmentV2PurchaseController(PendingPurchaseService service)
    {
        this.service = service;
    }

    @Log(title = "eBay补货2.0采购", businessType = BusinessType.INSERT)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishmentV2:list') and @ss.hasPermi('operations:ebayReplenishmentV2:purchase')")
    @PostMapping
    public AjaxResult submit(@Valid @RequestBody PendingPurchaseSubmitRequest request)
    {
        service.submit(request, getUsername());
        return success("已加入待采购清单");
    }
}
