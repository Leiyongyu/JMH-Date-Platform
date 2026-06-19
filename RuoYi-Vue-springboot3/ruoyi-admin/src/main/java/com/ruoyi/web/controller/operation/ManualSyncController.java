package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.operation.sync.AmzUnifiedSyncService;
import com.ruoyi.system.service.operation.sync.EbayUnifiedSyncService;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 手动同步控制器 —— 运营页面点击"拉取最新数据"按钮触发。
 * <p>
 * eBay 和 AMZ 各有两个端点：
 * <ul>
 *   <li>POST /operations/sync/manual/ebay           — eBay全量：拉源数据 + 刷新补货/跟价快照</li>
 *   <li>POST /operations/sync/manual/ebay/refresh-only  — eBay仅刷新快照</li>
 *   <li>POST /operations/sync/manual/amz            — AMZ全量</li>
 *   <li>POST /operations/sync/manual/amz/refresh-only   — AMZ仅刷新快照</li>
 * </ul>
 *
 * @author JMH
 */
@RestController
@RequestMapping("/operations/sync/manual")
public class ManualSyncController extends BaseController
{
    private final EbayUnifiedSyncService ebaySyncService;
    private final AmzUnifiedSyncService amzSyncService;

    public ManualSyncController(EbayUnifiedSyncService ebaySyncService,
                                 AmzUnifiedSyncService amzSyncService)
    {
        this.ebaySyncService = ebaySyncService;
        this.amzSyncService = amzSyncService;
    }

    /** eBay 全量同步 */
    @PostMapping("/ebay")
    public AjaxResult syncEbay()
    {
        Map<String, Object> result = ebaySyncService.syncAll("MANUAL", getUsername());
        String status = (String) result.get("parentStatus");
        if ("FAILED".equals(status))
            return error("eBay同步全部失败，请检查同步日志");
        if ("PARTIAL_SUCCESS".equals(status))
            return AjaxResult.success("eBay同步部分完成（" + result.get("successSteps") + "/"
                    + result.get("totalSteps") + "步成功）", result);
        return success(result);
    }

    /** eBay 仅刷新快照 */
    @PostMapping("/ebay/refresh-only")
    public AjaxResult refreshEbayOnly()
    {
        Map<String, Object> result = ebaySyncService.refreshOnly("MANUAL", getUsername());
        String status = (String) result.get("parentStatus");
        if ("FAILED".equals(status))
            return error("eBay快照刷新失败，请检查同步日志");
        return success(result);
    }

    /** AMZ 全量同步 */
    @PostMapping("/amz")
    public AjaxResult syncAmz()
    {
        Map<String, Object> result = amzSyncService.syncAll("MANUAL", getUsername());
        String status = (String) result.get("parentStatus");
        if ("FAILED".equals(status))
            return error("AMZ同步全部失败，请检查同步日志");
        if ("PARTIAL_SUCCESS".equals(status))
            return AjaxResult.success("AMZ同步部分完成（" + result.get("successSteps") + "/"
                    + result.get("totalSteps") + "步成功）", result);
        return success(result);
    }

    /** AMZ 仅刷新快照 */
    @PostMapping("/amz/refresh-only")
    public AjaxResult refreshAmzOnly()
    {
        Map<String, Object> result = amzSyncService.refreshOnly("MANUAL", getUsername());
        String status = (String) result.get("parentStatus");
        if ("FAILED".equals(status))
            return error("AMZ快照刷新失败，请检查同步日志");
        return success(result);
    }
}
