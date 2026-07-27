package com.ruoyi.system.service.operation.sync;

import com.ruoyi.system.domain.operation.TaskStatus;
import java.util.ArrayList;
import java.util.List;

/**
 * Unified result model for external sync tasks.
 */
public class OperationSyncResult
{
    // Backward-compatible string constants (mapped to TaskStatus)
    public static final String STATUS_RUNNING = TaskStatus.RUNNING.getValue();
    public static final String STATUS_SUCCESS = TaskStatus.SUCCESS.getValue();
    public static final String STATUS_PARTIAL = TaskStatus.PARTIAL.getValue();
    public static final String STATUS_PARTIAL_SUCCESS = TaskStatus.PARTIAL.getValue();
    public static final String STATUS_FAILED = TaskStatus.FAILED.getValue();
    public static final String STATUS_TIMEOUT = TaskStatus.FAILED.getValue();
    public static final String STATUS_CANCELLED = TaskStatus.CANCELLED.getValue();
    public static final String STATUS_SKIPPED = TaskStatus.SKIPPED.getValue();

    private String syncType;
    private String syncName;
    private String apiPath;
    private String status;
    private int totalCount;
    private int successCount;
    private int failCount;
    private String errorMessage;
    private long elapsedMs;
    private List<FailureItem> failures = new ArrayList<>();

    public static OperationSyncResult success(String syncType, String syncName, String apiPath,
                                               int totalCount, int successCount, long elapsedMs)
    {
        OperationSyncResult r = new OperationSyncResult();
        r.syncType = syncType;
        r.syncName = syncName;
        r.apiPath = apiPath;
        r.status = totalCount <= 0 && successCount <= 0 ? STATUS_FAILED : STATUS_SUCCESS;
        r.totalCount = totalCount;
        r.successCount = successCount;
        r.failCount = 0;
        if (STATUS_FAILED.equals(r.status))
        {
            r.errorMessage = "同步结果为空：总数0、成功0。请检查接口参数、返回数据或过滤条件。";
        }
        r.elapsedMs = elapsedMs;
        return r;
    }

    /**
     * 成功完成同步，允许接口在本次时间窗口内没有返回数据。
     * 适用于增量任务，避免“最近几天无新增”被误判为失败。
     */
    public static OperationSyncResult successAllowEmpty(String syncType, String syncName, String apiPath,
                                                        int totalCount, int successCount, long elapsedMs)
    {
        OperationSyncResult r = new OperationSyncResult();
        r.syncType = syncType;
        r.syncName = syncName;
        r.apiPath = apiPath;
        r.status = STATUS_SUCCESS;
        r.totalCount = totalCount;
        r.successCount = successCount;
        r.failCount = 0;
        r.elapsedMs = elapsedMs;
        return r;
    }

    public static OperationSyncResult failed(String syncType, String syncName, String apiPath,
                                              String errorMessage, long elapsedMs)
    {
        OperationSyncResult r = new OperationSyncResult();
        r.syncType = syncType;
        r.syncName = syncName;
        r.apiPath = apiPath;
        r.status = STATUS_FAILED;
        r.errorMessage = errorMessage;
        r.elapsedMs = elapsedMs;
        return r;
    }

    public static OperationSyncResult timeout(String syncType, String syncName, String apiPath,
                                               String errorMessage, long elapsedMs)
    {
        OperationSyncResult r = failed(syncType, syncName, apiPath, errorMessage, elapsedMs);
        r.status = STATUS_TIMEOUT;
        return r;
    }

    public static OperationSyncResult skipped(String syncType, String syncName, String apiPath,
                                               String reason, long elapsedMs)
    {
        OperationSyncResult r = failed(syncType, syncName, apiPath, reason, elapsedMs);
        r.status = STATUS_SKIPPED;
        return r;
    }

    public static OperationSyncResult partial(String syncType, String syncName, String apiPath,
                                               int totalCount, int successCount, int failCount,
                                               List<FailureItem> failures, long elapsedMs)
    {
        OperationSyncResult r = new OperationSyncResult();
        r.syncType = syncType;
        r.syncName = syncName;
        r.apiPath = apiPath;
        r.status = failCount <= 0 ? STATUS_SUCCESS : (successCount > 0 ? STATUS_PARTIAL : STATUS_FAILED);
        r.totalCount = totalCount;
        r.successCount = successCount;
        r.failCount = failCount;
        r.failures = failures != null ? failures : new ArrayList<>();
        r.elapsedMs = elapsedMs;
        return r;
    }

    public String toJobMessage(Long syncLogId)
    {
        StringBuilder sb = new StringBuilder();
        sb.append(syncName).append(" 执行");
        if (STATUS_SUCCESS.equals(status)) sb.append("成功");
        else if (STATUS_PARTIAL.equals(status) || STATUS_PARTIAL_SUCCESS.equals(status)) sb.append("部分成功");
        else if (STATUS_TIMEOUT.equals(status)) sb.append("超时");
        else if (STATUS_SKIPPED.equals(status)) sb.append("跳过");
        else sb.append("失败");
        sb.append("，总数").append(totalCount);
        sb.append("，成功").append(successCount);
        sb.append("，失败").append(failCount);
        sb.append("，耗时").append(String.format("%.1f", elapsedMs / 1000.0)).append("s");
        if (syncLogId != null) sb.append("，同步日志ID=").append(syncLogId);
        String detail = firstErrorSummary(180);
        if (detail != null && !detail.isEmpty()) sb.append("，").append(detail);
        return sb.toString();
    }

    public String toExceptionInfo()
    {
        StringBuilder sb = new StringBuilder();
        if (syncName != null && !syncName.isEmpty())
        {
            sb.append("任务：").append(syncName).append('\n');
        }
        if (syncType != null && !syncType.isEmpty())
        {
            sb.append("类型：").append(syncType).append('\n');
        }
        if (apiPath != null && !apiPath.isEmpty())
        {
            sb.append("接口：").append(apiPath).append('\n');
        }
        if (errorMessage != null && !errorMessage.isEmpty())
        {
            sb.append("错误：").append(errorMessage).append('\n');
        }
        if (failures != null && !failures.isEmpty())
        {
            sb.append("失败明细：\n");
            int limit = Math.min(failures.size(), 10);
            for (int i = 0; i < limit; i++)
            {
                FailureItem item = failures.get(i);
                sb.append(i + 1).append(". ")
                        .append(item.getKey() != null ? item.getKey() : "")
                        .append("：")
                        .append(item.getReason() != null ? item.getReason() : "")
                        .append('\n');
            }
            if (failures.size() > limit)
            {
                sb.append("... 还有").append(failures.size() - limit).append("条失败明细\n");
            }
        }
        return truncate(sb.toString(), 2000);
    }

    public String firstErrorSummary(int max)
    {
        String message = null;
        if (failures != null && !failures.isEmpty())
        {
            FailureItem item = failures.get(0);
            message = "失败步骤：" + safe(item.getKey()) + "，原因：" + safe(item.getReason());
        }
        else if (errorMessage != null && !errorMessage.isEmpty())
        {
            message = "错误：" + errorMessage;
        }
        return truncate(message, max);
    }

    public String getSyncType() { return syncType; }
    public void setSyncType(String syncType) { this.syncType = syncType; }

    public String getSyncName() { return syncName; }
    public void setSyncName(String syncName) { this.syncName = syncName; }

    public String getApiPath() { return apiPath; }
    public void setApiPath(String apiPath) { this.apiPath = apiPath; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public int getTotalCount() { return totalCount; }
    public void setTotalCount(int totalCount) { this.totalCount = totalCount; }

    public int getSuccessCount() { return successCount; }
    public void setSuccessCount(int successCount) { this.successCount = successCount; }

    public int getFailCount() { return failCount; }
    public void setFailCount(int failCount) { this.failCount = failCount; }

    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }

    public long getElapsedMs() { return elapsedMs; }
    public void setElapsedMs(long elapsedMs) { this.elapsedMs = elapsedMs; }

    public List<FailureItem> getFailures() { return failures; }
    public void setFailures(List<FailureItem> failures) { this.failures = failures; }

    private static String safe(String s)
    {
        return s != null ? s : "";
    }

    private static String truncate(String s, int max)
    {
        if (s == null || s.length() <= max) return s;
        return s.substring(0, max) + "...";
    }

    public static class FailureItem
    {
        private String key;
        private String reason;

        public FailureItem() {}

        public FailureItem(String key, String reason)
        {
            this.key = key;
            this.reason = reason;
        }

        public String getKey() { return key; }
        public void setKey(String key) { this.key = key; }

        public String getReason() { return reason; }
        public void setReason(String reason) { this.reason = reason; }
    }
}
