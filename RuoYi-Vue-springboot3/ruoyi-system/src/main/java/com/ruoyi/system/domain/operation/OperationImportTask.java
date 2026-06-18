package com.ruoyi.system.domain.operation;

import java.io.Serializable;
import java.util.Date;

public class OperationImportTask implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private String fileName;
    private String taskType;
    private String operator;
    private String status;
    private Integer totalRows;
    private Integer successRows;
    private Integer failRows;
    private String errorFilePath;
    private Date startTime;
    private Date endTime;
    private Date createTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getFileName() { return fileName; }
    public void setFileName(String fileName) { this.fileName = fileName; }
    public String getTaskType() { return taskType; }
    public void setTaskType(String taskType) { this.taskType = taskType; }
    public String getOperator() { return operator; }
    public void setOperator(String operator) { this.operator = operator; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Integer getTotalRows() { return totalRows; }
    public void setTotalRows(Integer totalRows) { this.totalRows = totalRows; }
    public Integer getSuccessRows() { return successRows; }
    public void setSuccessRows(Integer successRows) { this.successRows = successRows; }
    public Integer getFailRows() { return failRows; }
    public void setFailRows(Integer failRows) { this.failRows = failRows; }
    public String getErrorFilePath() { return errorFilePath; }
    public void setErrorFilePath(String errorFilePath) { this.errorFilePath = errorFilePath; }
    public Date getStartTime() { return startTime; }
    public void setStartTime(Date startTime) { this.startTime = startTime; }
    public Date getEndTime() { return endTime; }
    public void setEndTime(Date endTime) { this.endTime = endTime; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
}
