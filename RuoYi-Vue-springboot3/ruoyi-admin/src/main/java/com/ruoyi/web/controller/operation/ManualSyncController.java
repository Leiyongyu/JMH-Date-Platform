package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.operation.sync.AmzUnifiedSyncService;
import com.ruoyi.system.service.operation.sync.EbayUnifiedSyncService;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "手动同步")
@RestController
@RequestMapping("/operations/sync/manual")
public class ManualSyncController extends BaseController
{
    private final EbayUnifiedSyncService ebaySyncService;
    private final AmzUnifiedSyncService amzSyncService;

    public ManualSyncController(EbayUnifiedSyncService ebaySyncService, AmzUnifiedSyncService amzSyncService)
    {
        this.ebaySyncService = ebaySyncService;
        this.amzSyncService = amzSyncService;
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:sync')")
    @PostMapping("/ebay")
    public AjaxResult syncEbay()
    {
        return handle(ebaySyncService.syncAll("MANUAL", getUsername()), "eBay");
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:sync')")
    @PostMapping("/ebay/refresh-only")
    public AjaxResult refreshEbayOnly()
    {
        return handle(ebaySyncService.refreshOnly("MANUAL", getUsername()), "eBay");
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:sync')")
    @PostMapping("/amz")
    public AjaxResult syncAmz()
    {
        return handle(amzSyncService.syncAll("MANUAL", getUsername()), "AMZ");
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:sync')")
    @PostMapping("/amz/refresh-only")
    public AjaxResult refreshAmzOnly()
    {
        return handle(amzSyncService.refreshOnly("MANUAL", getUsername()), "AMZ");
    }

    private AjaxResult handle(Map<String, Object> result, String label)
    {
        String status = (String) result.get("parentStatus");
        if ("BUSY".equals(status)) return error((String) result.get("msg"));
        if ("FAILED".equals(status)) return error(label + "同步全部失败，请检查同步日志");
        if ("PARTIAL_SUCCESS".equals(status))
            return AjaxResult.success(label + "同步部分完成：" + result.get("successSteps") + "/"
                    + result.get("totalSteps") + " 步成功", result);
        return success(result);
    }
}
