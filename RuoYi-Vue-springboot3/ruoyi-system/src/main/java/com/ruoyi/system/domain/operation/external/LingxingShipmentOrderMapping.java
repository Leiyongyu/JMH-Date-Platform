package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.time.LocalDateTime;

/** 领星FBA货件单号与发货单号映射。 */
public class LingxingShipmentOrderMapping implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String shipmentId;
    private String shipmentSn;
    private Long shipmentListId;
    private Long sid;
    private String storeName;
    private Integer orderStatus;
    private String shipmentStatus;
    private Integer isDelete;
    private LocalDateTime remoteCreateTime;
    private LocalDateTime remoteUpdateTime;
    private LocalDateTime syncTime;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getShipmentId() { return shipmentId; }
    public void setShipmentId(String shipmentId) { this.shipmentId = shipmentId; }
    public String getShipmentSn() { return shipmentSn; }
    public void setShipmentSn(String shipmentSn) { this.shipmentSn = shipmentSn; }
    public Long getShipmentListId() { return shipmentListId; }
    public void setShipmentListId(Long shipmentListId) { this.shipmentListId = shipmentListId; }
    public Long getSid() { return sid; }
    public void setSid(Long sid) { this.sid = sid; }
    public String getStoreName() { return storeName; }
    public void setStoreName(String storeName) { this.storeName = storeName; }
    public Integer getOrderStatus() { return orderStatus; }
    public void setOrderStatus(Integer orderStatus) { this.orderStatus = orderStatus; }
    public String getShipmentStatus() { return shipmentStatus; }
    public void setShipmentStatus(String shipmentStatus) { this.shipmentStatus = shipmentStatus; }
    public Integer getIsDelete() { return isDelete; }
    public void setIsDelete(Integer isDelete) { this.isDelete = isDelete; }
    public LocalDateTime getRemoteCreateTime() { return remoteCreateTime; }
    public void setRemoteCreateTime(LocalDateTime remoteCreateTime) { this.remoteCreateTime = remoteCreateTime; }
    public LocalDateTime getRemoteUpdateTime() { return remoteUpdateTime; }
    public void setRemoteUpdateTime(LocalDateTime remoteUpdateTime) { this.remoteUpdateTime = remoteUpdateTime; }
    public LocalDateTime getSyncTime() { return syncTime; }
    public void setSyncTime(LocalDateTime syncTime) { this.syncTime = syncTime; }
    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
    public LocalDateTime getUpdateTime() { return updateTime; }
    public void setUpdateTime(LocalDateTime updateTime) { this.updateTime = updateTime; }
}
