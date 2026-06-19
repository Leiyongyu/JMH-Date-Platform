package com.ruoyi.system.domain.operation;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 业务数据同步执行日志 —— 增强版，记录每次同步的接口、结果、失败明细。
 *
 * @author JMH
 */
public class DataSyncLog implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String syncType;
    private String syncName;
    private String apiPath;         // ★ 新增：调用的 API 路径
    private String status;          // RUNNING / SUCCESS / FAILED
    private String triggerType;     // MANUAL / JOB
    private String operator;
    private Long jobId;             // ★ 新增：若依 sys_job.job_id
    private Long jobLogId;          // ★ 新增：若依 sys_job_log.job_log_id
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private int totalCount;
    private int successCount;
    private int failCount;
    private String errorMessage;
    private String requestParams;
    private String detailJson;      // ★ 新增：完整执行详情 JSON
    private String failedJson;      // ★ 新增：失败明细 JSON
    private Long parentId;           // ★ 新增：父日志ID，用于父子步骤关联
    private LocalDateTime createTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getSyncType() { return syncType; }
    public void setSyncType(String syncType) { this.syncType = syncType; }

    public String getSyncName() { return syncName; }
    public void setSyncName(String syncName) { this.syncName = syncName; }

    public String getApiPath() { return apiPath; }
    public void setApiPath(String apiPath) { this.apiPath = apiPath; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getTriggerType() { return triggerType; }
    public void setTriggerType(String triggerType) { this.triggerType = triggerType; }

    public String getOperator() { return operator; }
    public void setOperator(String operator) { this.operator = operator; }

    public Long getJobId() { return jobId; }
    public void setJobId(Long jobId) { this.jobId = jobId; }

    public Long getJobLogId() { return jobLogId; }
    public void setJobLogId(Long jobLogId) { this.jobLogId = jobLogId; }

    public LocalDateTime getStartTime() { return startTime; }
    public void setStartTime(LocalDateTime startTime) { this.startTime = startTime; }

    public LocalDateTime getEndTime() { return endTime; }
    public void setEndTime(LocalDateTime endTime) { this.endTime = endTime; }

    public int getTotalCount() { return totalCount; }
    public void setTotalCount(int totalCount) { this.totalCount = totalCount; }

    public int getSuccessCount() { return successCount; }
    public void setSuccessCount(int successCount) { this.successCount = successCount; }

    public int getFailCount() { return failCount; }
    public void setFailCount(int failCount) { this.failCount = failCount; }

    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }

    public String getRequestParams() { return requestParams; }
    public void setRequestParams(String requestParams) { this.requestParams = requestParams; }

    public String getDetailJson() { return detailJson; }
    public void setDetailJson(String detailJson) { this.detailJson = detailJson; }

    public String getFailedJson() { return failedJson; }
    public void setFailedJson(String failedJson) { this.failedJson = failedJson; }

    public Long getParentId() { return parentId; }
    public void setParentId(Long parentId) { this.parentId = parentId; }

    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
}
