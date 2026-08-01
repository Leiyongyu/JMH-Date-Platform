package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.time.LocalDateTime;

/** STA装箱提交记录及待提交列表视图。 */
public class CustomsPackingSubmission implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String inboundPlanId;
    private Long sid;
    private Integer positionType;
    private String status;
    private String taskId;
    private String payloadHash;
    private String requestBody;
    private String initialResponseBody;
    private String finalResponseBody;
    private String requestId;
    private String errorMessage;
    private Integer attemptCount;
    private String operator;
    private LocalDateTime submitTime;
    private LocalDateTime successTime;
    private LocalDateTime failedTime;
    private LocalDateTime lastPollTime;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;

    /** 以下字段由待提交聚合查询返回，不直接写入提交表。 */
    private Integer savedShipmentCount;
    private Integer expectedShipmentCount;
    private Integer boxCount;
    private LocalDateTime lastSavedTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getInboundPlanId() { return inboundPlanId; }
    public void setInboundPlanId(String inboundPlanId) { this.inboundPlanId = inboundPlanId; }
    public Long getSid() { return sid; }
    public void setSid(Long sid) { this.sid = sid; }
    public Integer getPositionType() { return positionType; }
    public void setPositionType(Integer positionType) { this.positionType = positionType; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getTaskId() { return taskId; }
    public void setTaskId(String taskId) { this.taskId = taskId; }
    public String getPayloadHash() { return payloadHash; }
    public void setPayloadHash(String payloadHash) { this.payloadHash = payloadHash; }
    public String getRequestBody() { return requestBody; }
    public void setRequestBody(String requestBody) { this.requestBody = requestBody; }
    public String getInitialResponseBody() { return initialResponseBody; }
    public void setInitialResponseBody(String initialResponseBody) { this.initialResponseBody = initialResponseBody; }
    public String getFinalResponseBody() { return finalResponseBody; }
    public void setFinalResponseBody(String finalResponseBody) { this.finalResponseBody = finalResponseBody; }
    public String getRequestId() { return requestId; }
    public void setRequestId(String requestId) { this.requestId = requestId; }
    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }
    public Integer getAttemptCount() { return attemptCount; }
    public void setAttemptCount(Integer attemptCount) { this.attemptCount = attemptCount; }
    public String getOperator() { return operator; }
    public void setOperator(String operator) { this.operator = operator; }
    public LocalDateTime getSubmitTime() { return submitTime; }
    public void setSubmitTime(LocalDateTime submitTime) { this.submitTime = submitTime; }
    public LocalDateTime getSuccessTime() { return successTime; }
    public void setSuccessTime(LocalDateTime successTime) { this.successTime = successTime; }
    public LocalDateTime getFailedTime() { return failedTime; }
    public void setFailedTime(LocalDateTime failedTime) { this.failedTime = failedTime; }
    public LocalDateTime getLastPollTime() { return lastPollTime; }
    public void setLastPollTime(LocalDateTime lastPollTime) { this.lastPollTime = lastPollTime; }
    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
    public LocalDateTime getUpdateTime() { return updateTime; }
    public void setUpdateTime(LocalDateTime updateTime) { this.updateTime = updateTime; }
    public Integer getSavedShipmentCount() { return savedShipmentCount; }
    public void setSavedShipmentCount(Integer savedShipmentCount) { this.savedShipmentCount = savedShipmentCount; }
    public Integer getExpectedShipmentCount() { return expectedShipmentCount; }
    public void setExpectedShipmentCount(Integer expectedShipmentCount) { this.expectedShipmentCount = expectedShipmentCount; }
    public Integer getBoxCount() { return boxCount; }
    public void setBoxCount(Integer boxCount) { this.boxCount = boxCount; }
    public LocalDateTime getLastSavedTime() { return lastSavedTime; }
    public void setLastSavedTime(LocalDateTime lastSavedTime) { this.lastSavedTime = lastSavedTime; }
}
