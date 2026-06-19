package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.system.service.operation.sync.AmzUnifiedSyncService;
import com.ruoyi.system.service.operation.sync.EbayUnifiedSyncService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Map;
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
    private final RedisCache redisCache;

    public ManualSyncController(EbayUnifiedSyncService ebaySyncService,
                                 AmzUnifiedSyncService amzSyncService,
                                 RedisCache redisCache)
    {
        this.ebaySyncService = ebaySyncService;
        this.amzSyncService = amzSyncService;
        this.redisCache = redisCache;
    }

    /** eBay 全量同步 */
    @PostMapping("/ebay")
    public AjaxResult syncEbay()
    {
        return withLock("lock:sync:ebay", 600, "eBay数据同步正在执行中，请稍后再试", () -> {
            Map<String, Object> result = ebaySyncService.syncAll("MANUAL", getUsername());
            String status = (String) result.get("parentStatus");
            if ("FAILED".equals(status))
                return error("eBay同步全部失败，请检查同步日志");
            if ("PARTIAL_SUCCESS".equals(status))
                return AjaxResult.success("eBay同步部分完成（" + result.get("successSteps") + "/"
                        + result.get("totalSteps") + "步成功）", result);
            return success(result);
        });
    }

    /** AMZ 全量同步 */
    @PostMapping("/amz")
    public AjaxResult syncAmz()
    {
        return withLock("lock:sync:amz", 600, "AMZ数据同步正在执行中，请稍后再试", () -> {
            Map<String, Object> result = amzSyncService.syncAll("MANUAL", getUsername());
            String status = (String) result.get("parentStatus");
            if ("FAILED".equals(status))
                return error("AMZ同步全部失败，请检查同步日志");
            if ("PARTIAL_SUCCESS".equals(status))
                return AjaxResult.success("AMZ同步部分完成（" + result.get("successSteps") + "/"
                        + result.get("totalSteps") + "步成功）", result);
            return success(result);
        });
    }

    // ==================== 锁工具 ====================

    @FunctionalInterface
    private interface LockedAction { AjaxResult run(); }

    private AjaxResult withLock(String key, long timeoutSec, String busyMsg, LockedAction action)
    {
        if (!redisCache.tryLock(key, timeoutSec))
        {
            return error(busyMsg);
        }
        try
        {
            return action.run();
        }
        finally
        {
            redisCache.unlock(key);
        }
    }
}
