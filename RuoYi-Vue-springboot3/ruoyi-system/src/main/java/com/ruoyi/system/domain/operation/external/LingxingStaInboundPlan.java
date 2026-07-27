package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.time.LocalDateTime;

/** 领星STA任务主数据。 */
public class LingxingStaInboundPlan implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String recordKey;
    private String inboundPlanId;
    private Long sid;
    private String planName;
    private String status;
    private Integer positionType;
    private LocalDateTime gmtCreate;
    private LocalDateTime gmtModified;
    private LocalDateTime syncTime;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getRecordKey() { return recordKey; }
    public void setRecordKey(String recordKey) { this.recordKey = recordKey; }
    public String getInboundPlanId() { return inboundPlanId; }
    public void setInboundPlanId(String inboundPlanId) { this.inboundPlanId = inboundPlanId; }
    public Long getSid() { return sid; }
    public void setSid(Long sid) { this.sid = sid; }
    public String getPlanName() { return planName; }
    public void setPlanName(String planName) { this.planName = planName; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Integer getPositionType() { return positionType; }
    public void setPositionType(Integer positionType) { this.positionType = positionType; }
    public LocalDateTime getGmtCreate() { return gmtCreate; }
    public void setGmtCreate(LocalDateTime gmtCreate) { this.gmtCreate = gmtCreate; }
    public LocalDateTime getGmtModified() { return gmtModified; }
    public void setGmtModified(LocalDateTime gmtModified) { this.gmtModified = gmtModified; }
    public LocalDateTime getSyncTime() { return syncTime; }
    public void setSyncTime(LocalDateTime syncTime) { this.syncTime = syncTime; }
    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
    public LocalDateTime getUpdateTime() { return updateTime; }
    public void setUpdateTime(LocalDateTime updateTime) { this.updateTime = updateTime; }
}
