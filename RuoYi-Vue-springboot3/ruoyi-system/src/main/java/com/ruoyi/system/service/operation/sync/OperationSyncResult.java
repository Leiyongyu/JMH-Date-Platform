package com.ruoyi.system.service.operation.sync;

import java.util.ArrayList;
import java.util.List;

/**
 * 统一同步结果模型 —— 每个接口同步任务都返回此对象，用于统一写入
 * data_sync_log 和增强 sys_job_log 的 job_message。
 *
 * @author JMH
 */
public class OperationSyncResult
{
    /** 同步类型标识，如 warehouse / ebay_listing / goodcang_grn */
    private String syncType;

    /** 同步名称（中文），如 "领星-仓库信息" */
    private String syncName;

    /** 调用的 API 路径，如 erp/sc/data/local_inventory/warehouse */
    private String apiPath;

    /** 执行状态：RUNNING / SUCCESS / FAILED */
    private String status;

    /** 本次拉取到的总条数 */
    private int totalCount;

    /** 成功写入/更新的条数 */
    private int successCount;

    /** 失败条数 */
    private int failCount;

    /** 全局错误信息（如整个接口调用失败） */
    private String errorMessage;

    /** 执行耗时（毫秒） */
    private long elapsedMs;

    /** 失败明细列表 */
    private List<FailureItem> failures = new ArrayList<>();

    // ========== 工厂方法 ==========

    public static OperationSyncResult success(String syncType, String syncName, String apiPath,
                                               int totalCount, int successCount, long elapsedMs)
    {
        OperationSyncResult r = new OperationSyncResult();
        r.syncType = syncType;
        r.syncName = syncName;
        r.apiPath = apiPath;
        r.status = "SUCCESS";
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
        r.status = "FAILED";
        r.errorMessage = errorMessage;
        r.elapsedMs = elapsedMs;
        return r;
    }

    /** 部分失败：有成功有失败 */
    public static OperationSyncResult partial(String syncType, String syncName, String apiPath,
                                               int totalCount, int successCount, int failCount,
                                               List<FailureItem> failures, long elapsedMs)
    {
        OperationSyncResult r = new OperationSyncResult();
        r.syncType = syncType;
        r.syncName = syncName;
        r.apiPath = apiPath;
        r.status = failCount >= totalCount ? "FAILED" : "SUCCESS";
        r.totalCount = totalCount;
        r.successCount = successCount;
        r.failCount = failCount;
        r.failures = failures != null ? failures : new ArrayList<>();
        r.elapsedMs = elapsedMs;
        return r;
    }

    /**
     * 生成用于 sys_job_log.job_message 的增强描述文本。
     * 示例：领星-仓库信息 执行成功，总数120，成功118，失败2，耗时12.3s，同步日志ID=45
     */
    public String toJobMessage(Long syncLogId)
    {
        StringBuilder sb = new StringBuilder();
        sb.append(syncName).append(" 执行");
        if ("SUCCESS".equals(status))
        {
            sb.append("成功");
        }
        else
        {
            sb.append("失败");
        }
        sb.append("，总数").append(totalCount);
        sb.append("，成功").append(successCount);
        sb.append("，失败").append(failCount);
        sb.append("，耗时").append(String.format("%.1f", elapsedMs / 1000.0)).append("s");
        if (syncLogId != null)
        {
            sb.append("，同步日志ID=").append(syncLogId);
        }
        return sb.toString();
    }

    // ========== getters / setters ==========

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

    /**
     * 单条失败明细。
     */
    public static class FailureItem
    {
        private String key;       // 失败项的唯一标识，如 SKU / receiving_code
        private String reason;    // 失败原因

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
