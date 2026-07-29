package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.time.LocalDateTime;

/** 单个发货单的领星费用更新日志。 */
public class CustomsShipmentFeeImportLog implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private Long batchId;
    private String businessType;
    private String batchNo;
    private String originalFileName;
    private String shipmentId;
    private String orderSn;
    private String sourceRows;
    private Integer sourceRowCount;
    private String status;
    private String errorStage;
    private String errorCode;
    private String errorMessage;
    private String exceptionType;
    private String stackTrace;
    private String requestId;
    private String lingxingResponseTime;
    private Integer attemptCount;
    private String requestBody;
    private String responseBody;
    private String sourceData;
    private String operator;
    private LocalDateTime uploadTime;
    private LocalDateTime startTime;
    private LocalDateTime successTime;
    private LocalDateTime failedTime;
    private Long durationMs;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getBatchId() { return batchId; }
    public void setBatchId(Long batchId) { this.batchId = batchId; }
    public String getBusinessType() { return businessType; }
    public void setBusinessType(String businessType) { this.businessType = businessType; }
    public String getBatchNo() { return batchNo; }
    public void setBatchNo(String batchNo) { this.batchNo = batchNo; }
    public String getOriginalFileName() { return originalFileName; }
    public void setOriginalFileName(String originalFileName) { this.originalFileName = originalFileName; }
    public String getShipmentId() { return shipmentId; }
    public void setShipmentId(String shipmentId) { this.shipmentId = shipmentId; }
    public String getOrderSn() { return orderSn; }
    public void setOrderSn(String orderSn) { this.orderSn = orderSn; }
    public String getSourceRows() { return sourceRows; }
    public void setSourceRows(String sourceRows) { this.sourceRows = sourceRows; }
    public Integer getSourceRowCount() { return sourceRowCount; }
    public void setSourceRowCount(Integer sourceRowCount) { this.sourceRowCount = sourceRowCount; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getErrorStage() { return errorStage; }
    public void setErrorStage(String errorStage) { this.errorStage = errorStage; }
    public String getErrorCode() { return errorCode; }
    public void setErrorCode(String errorCode) { this.errorCode = errorCode; }
    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }
    public String getExceptionType() { return exceptionType; }
    public void setExceptionType(String exceptionType) { this.exceptionType = exceptionType; }
    public String getStackTrace() { return stackTrace; }
    public void setStackTrace(String stackTrace) { this.stackTrace = stackTrace; }
    public String getRequestId() { return requestId; }
    public void setRequestId(String requestId) { this.requestId = requestId; }
    public String getLingxingResponseTime() { return lingxingResponseTime; }
    public void setLingxingResponseTime(String lingxingResponseTime) { this.lingxingResponseTime = lingxingResponseTime; }
    public Integer getAttemptCount() { return attemptCount; }
    public void setAttemptCount(Integer attemptCount) { this.attemptCount = attemptCount; }
    public String getRequestBody() { return requestBody; }
    public void setRequestBody(String requestBody) { this.requestBody = requestBody; }
    public String getResponseBody() { return responseBody; }
    public void setResponseBody(String responseBody) { this.responseBody = responseBody; }
    public String getSourceData() { return sourceData; }
    public void setSourceData(String sourceData) { this.sourceData = sourceData; }
    public String getOperator() { return operator; }
    public void setOperator(String operator) { this.operator = operator; }
    public LocalDateTime getUploadTime() { return uploadTime; }
    public void setUploadTime(LocalDateTime uploadTime) { this.uploadTime = uploadTime; }
    public LocalDateTime getStartTime() { return startTime; }
    public void setStartTime(LocalDateTime startTime) { this.startTime = startTime; }
    public LocalDateTime getSuccessTime() { return successTime; }
    public void setSuccessTime(LocalDateTime successTime) { this.successTime = successTime; }
    public LocalDateTime getFailedTime() { return failedTime; }
    public void setFailedTime(LocalDateTime failedTime) { this.failedTime = failedTime; }
    public Long getDurationMs() { return durationMs; }
    public void setDurationMs(Long durationMs) { this.durationMs = durationMs; }
    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
    public LocalDateTime getUpdateTime() { return updateTime; }
    public void setUpdateTime(LocalDateTime updateTime) { this.updateTime = updateTime; }
}
