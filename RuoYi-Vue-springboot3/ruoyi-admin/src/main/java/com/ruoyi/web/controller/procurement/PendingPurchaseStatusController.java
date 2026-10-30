package com.ruoyi.web.controller.procurement;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.procurement.PendingPurchaseStatusService;
import com.ruoyi.web.task.PendingPurchaseStatusTask;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/procurement/pending-purchase/po-status")
public class PendingPurchaseStatusController extends BaseController
{
    private final PendingPurchaseStatusService service;
    private final PendingPurchaseStatusTask task;
    private final RedisCache redis;
    public PendingPurchaseStatusController(PendingPurchaseStatusService service, PendingPurchaseStatusTask task, RedisCache redis)
    { this.service = service; this.task = task; this.redis = redis; }

    @PreAuthorize("@ss.hasPermi('procurement:pendingPurchase:list')")
    @GetMapping
    public AjaxResult state() { return success(service.state()); }

    @PreAuthorize("@ss.hasPermi('procurement:pendingPurchase:list')")
    @GetMapping("/summary")
    public AjaxResult summary(@RequestParam List<Long> ids) { return success(service.summary(ids)); }

    @PreAuthorize("@ss.hasPermi('procurement:pendingPurchase:list')")
    @GetMapping("/{id}")
    public AjaxResult details(@PathVariable Long id) { return success(service.details(id)); }

    @Log(title = "同步待采购采购单状态", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('procurement:pendingPurchase:syncStatus')")
    @PostMapping("/sync")
    public AjaxResult sync()
    {
        if (redis.hasKey("lock:sync:lingxing:ebay")) return error("eBay数据同步正在执行，请稍后重试");
        task.manual(getUsername());
        return success("已提交后台同步，可继续查看上次成功数据");
    }
}
