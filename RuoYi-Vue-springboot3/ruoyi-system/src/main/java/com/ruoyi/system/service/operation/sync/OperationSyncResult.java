package com.ruoyi.system.service.operation.sync;

import java.util.ArrayList;
import java.util.List;

/**
 * Unified result model for external sync tasks.
 */
public class OperationSyncResult
{
    public static final String STATUS_RUNNING = "RUNNING";
    public static final String STATUS_SUCCESS = "SUCCESS";
    public static final String STATUS_PARTIAL = "PARTIAL";
    public static final String STATUS_FAILED = "FAILED";
    public static final String STATUS_TIMEOUT = "TIMEOUT";
    public static final String STATUS_CANCELLED = "CANCELLED";
    public static final String STATUS_SKIPPED = "SKIPPED";

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
        else if (STATUS_PARTIAL.equals(status)) sb.append("部分成功");
        else if (STATUS_TIMEOUT.equals(status)) sb.append("超时");
        else if (STATUS_SKIPPED.equals(status)) sb.append("跳过");
        else sb.append("失败");
        sb.append("，总数").append(totalCount);
        sb.append("，成功").append(successCount);
        sb.append("，失败").append(failCount);
        sb.append("，耗时").append(String.format("%.1f", elapsedMs / 1000.0)).append("s");
        if (syncLogId != null) sb.append("，同步日志ID=").append(syncLogId);
        return sb.toString();
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
