package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.time.LocalDateTime;

/** 领星STA任务货件明细。 */
public class LingxingStaInboundPlanShipment implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String recordKey;
    private String inboundPlanId;
    private Integer shipmentIndex;
    private String shipmentId;
    private String shipmentConfirmationId;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getRecordKey() { return recordKey; }
    public void setRecordKey(String recordKey) { this.recordKey = recordKey; }
    public String getInboundPlanId() { return inboundPlanId; }
    public void setInboundPlanId(String inboundPlanId) { this.inboundPlanId = inboundPlanId; }
    public Integer getShipmentIndex() { return shipmentIndex; }
    public void setShipmentIndex(Integer shipmentIndex) { this.shipmentIndex = shipmentIndex; }
    public String getShipmentId() { return shipmentId; }
    public void setShipmentId(String shipmentId) { this.shipmentId = shipmentId; }
    public String getShipmentConfirmationId() { return shipmentConfirmationId; }
    public void setShipmentConfirmationId(String shipmentConfirmationId)
    {
        this.shipmentConfirmationId = shipmentConfirmationId;
    }
    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
    public LocalDateTime getUpdateTime() { return updateTime; }
    public void setUpdateTime(LocalDateTime updateTime) { this.updateTime = updateTime; }
}
