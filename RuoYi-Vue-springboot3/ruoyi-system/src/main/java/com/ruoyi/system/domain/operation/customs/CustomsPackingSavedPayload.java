package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.time.LocalDateTime;

/** 最近一次保存成功的单个STA货件装箱请求快照。 */
public class CustomsPackingSavedPayload implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long logId;
    private String inboundPlanId;
    private String shipmentId;
    private Long sid;
    private String requestBody;
    private LocalDateTime successTime;

    public Long getLogId() { return logId; }
    public void setLogId(Long logId) { this.logId = logId; }
    public String getInboundPlanId() { return inboundPlanId; }
    public void setInboundPlanId(String inboundPlanId) { this.inboundPlanId = inboundPlanId; }
    public String getShipmentId() { return shipmentId; }
    public void setShipmentId(String shipmentId) { this.shipmentId = shipmentId; }
    public Long getSid() { return sid; }
    public void setSid(Long sid) { this.sid = sid; }
    public String getRequestBody() { return requestBody; }
    public void setRequestBody(String requestBody) { this.requestBody = requestBody; }
    public LocalDateTime getSuccessTime() { return successTime; }
    public void setSuccessTime(LocalDateTime successTime) { this.successTime = successTime; }
}
