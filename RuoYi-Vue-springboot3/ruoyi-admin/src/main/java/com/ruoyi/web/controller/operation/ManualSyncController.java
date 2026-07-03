package com.ruoyi.web.controller.operation;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.domain.operation.TaskStatus;
import com.ruoyi.system.service.operation.sync.SyncTaskAsyncService;
import com.ruoyi.system.service.operation.sync.SyncTaskAsyncService.SyncSubmission;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "手动同步")
@RestController
@RequestMapping("/operations/sync/manual")
public class ManualSyncController extends BaseController
{
    private final SyncTaskAsyncService asyncSyncService;

    public ManualSyncController(SyncTaskAsyncService asyncSyncService)
    {
        this.asyncSyncService = asyncSyncService;
    }

    /** Submit eBay sync — returns immediately with submissionId for polling. */
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:sync')")
    @PostMapping("/ebay")
    public AjaxResult syncEbay()
    {
        String sid = asyncSyncService.submitEbay("MANUAL", getUsername(), "full");
        return submitted(sid, "eBay全量同步");
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:sync')")
    @PostMapping("/ebay/refresh-only")
    public AjaxResult refreshEbayOnly()
    {
        String sid = asyncSyncService.submitEbay("MANUAL", getUsername(), "refresh");
        return submitted(sid, "eBay快照刷新");
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:sync')")
    @PostMapping("/amz")
    public AjaxResult syncAmz()
    {
        String sid = asyncSyncService.submitAmz("MANUAL", getUsername(), "full");
        return submitted(sid, "AMZ全量同步");
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:sync')")
    @PostMapping("/amz/refresh-only")
    public AjaxResult refreshAmzOnly()
    {
        String sid = asyncSyncService.submitAmz("MANUAL", getUsername(), "refresh");
        return submitted(sid, "AMZ快照刷新");
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:sync')")
    @PostMapping("/stock-order")
    public AjaxResult syncStockOrder()
    {
        String sid = asyncSyncService.submitStockOrder(getUsername());
        return submitted(sid, "备货单同步");
    }

    /** Poll submission status. Returns real logId once the async task completes. */
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:sync') || @ss.hasPermi('operations:amzReplenishment:sync')")
    @GetMapping("/status/{submissionId}")
    public AjaxResult status(@PathVariable String submissionId)
    {
        SyncSubmission sub = asyncSyncService.getSubmission(submissionId);
        if (sub == null) return error("任务不存在或已过期: " + submissionId);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("submissionId", sub.getSubmissionId());
        data.put("syncType", sub.getSyncType());
        data.put("status", sub.getStatus());
        data.put("parentLogId", sub.getParentLogId());
        data.put("parentStatus", sub.getParentStatus());
        data.put("totalSteps", sub.getTotalSteps());
        data.put("successSteps", sub.getSuccessSteps());
        data.put("failedSteps", sub.getFailedSteps());
        data.put("elapsedSeconds", sub.getElapsedSeconds());
        data.put("errorMessage", sub.getErrorMessage());
        data.put("isTerminal", sub.isTerminal());

        if (sub.isTerminal())
        {
            String msg = TaskStatus.PARTIAL.getValue().equals(sub.getStatus())
                    ? "同步部分完成：" + sub.getSuccessSteps() + "/" + sub.getTotalSteps() + " 步成功"
                    : TaskStatus.FAILED.getValue().equals(sub.getStatus())
                    ? "同步失败：" + (sub.getErrorMessage() != null ? sub.getErrorMessage() : "未知错误")
                    : "同步完成";
            return AjaxResult.success(msg, data);
        }
        return AjaxResult.success("同步进行中…", data);
    }

    private AjaxResult submitted(String submissionId, String label)
    {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("submissionId", submissionId);
        data.put("status", "PENDING");
        return AjaxResult.success(label + "任务已提交", data);
    }
}
