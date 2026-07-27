package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;

/** 根据货件号组装领星STA装箱请求所需的关联信息。 */
public class LingxingStaPackingContext implements Serializable
{
    private static final long serialVersionUID = 1L;

    private String recordKey;
    private String inboundPlanId;
    private Long sid;
    private String shipmentId;
    private String shipmentConfirmationId;

    public String getRecordKey() { return recordKey; }
    public void setRecordKey(String recordKey) { this.recordKey = recordKey; }
    public String getInboundPlanId() { return inboundPlanId; }
    public void setInboundPlanId(String inboundPlanId) { this.inboundPlanId = inboundPlanId; }
    public Long getSid() { return sid; }
    public void setSid(Long sid) { this.sid = sid; }
    public String getShipmentId() { return shipmentId; }
    public void setShipmentId(String shipmentId) { this.shipmentId = shipmentId; }
    public String getShipmentConfirmationId() { return shipmentConfirmationId; }
    public void setShipmentConfirmationId(String shipmentConfirmationId)
    {
        this.shipmentConfirmationId = shipmentConfirmationId;
    }
}
