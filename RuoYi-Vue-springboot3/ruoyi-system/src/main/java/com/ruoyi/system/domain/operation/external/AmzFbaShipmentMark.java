package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.util.Date;

public class AmzFbaShipmentMark implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private String msku;
    private String shipmentId;
    private String remark;
    private Integer confirmed;
    private Date updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getMsku() { return msku; }
    public void setMsku(String msku) { this.msku = msku; }
    public String getShipmentId() { return shipmentId; }
    public void setShipmentId(String shipmentId) { this.shipmentId = shipmentId; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
    public Integer getConfirmed() { return confirmed; }
    public void setConfirmed(Integer confirmed) { this.confirmed = confirmed; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date updateTime) { this.updateTime = updateTime; }
}
