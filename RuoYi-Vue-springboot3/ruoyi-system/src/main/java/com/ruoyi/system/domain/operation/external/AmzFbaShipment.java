package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.util.Date;

/**
 * Amazon FBA 货件明细表 —— 领星 API /erp/sc/data/fba_report/shipmentList
 */
public class AmzFbaShipment implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private Integer sid;
    private String storeName;
    private String username;
    private String shipmentId;
    private String shipmentName;
    private String shipmentStatus;
    private String msku;
    private String sku;
    private Integer quantityShipped;
    private Integer initQuantityShipped;
    private Integer quantityReceived;
    private Integer quantityShippedLocal;
    private Integer declaredDiff;
    private Date gmtCreate;
    private Date gmtModified;
    private Date workingTime;
    private Date shippedTime;
    private Date receivingTime;
    private Date closedTime;
    private String remark;
    private Integer confirmed;
    private Date createTime;
    private String shipToName;
    private String shipToCountryCode;
    private String shipToState;
    private String shipToCity;
    private String shipToRegion;
    private String shipToAddressLine1;
    private String shipToAddressLine2;
    private String shipToPostalCode;
    private String shipToDoorplate;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Integer getSid() { return sid; }
    public void setSid(Integer sid) { this.sid = sid; }
    public String getStoreName() { return storeName; }
    public void setStoreName(String storeName) { this.storeName = storeName; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getShipmentId() { return shipmentId; }
    public void setShipmentId(String shipmentId) { this.shipmentId = shipmentId; }
    public String getShipmentName() { return shipmentName; }
    public void setShipmentName(String shipmentName) { this.shipmentName = shipmentName; }
    public String getShipmentStatus() { return shipmentStatus; }
    public void setShipmentStatus(String shipmentStatus) { this.shipmentStatus = shipmentStatus; }
    public String getMsku() { return msku; }
    public void setMsku(String msku) { this.msku = msku; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public Integer getQuantityShipped() { return quantityShipped; }
    public void setQuantityShipped(Integer quantityShipped) { this.quantityShipped = quantityShipped; }
    public Integer getInitQuantityShipped() { return initQuantityShipped; }
    public void setInitQuantityShipped(Integer initQuantityShipped) { this.initQuantityShipped = initQuantityShipped; }
    public Integer getQuantityReceived() { return quantityReceived; }
    public void setQuantityReceived(Integer quantityReceived) { this.quantityReceived = quantityReceived; }
    public Integer getQuantityShippedLocal() { return quantityShippedLocal; }
    public void setQuantityShippedLocal(Integer quantityShippedLocal) { this.quantityShippedLocal = quantityShippedLocal; }
    public Integer getDeclaredDiff() { return declaredDiff; }
    public void setDeclaredDiff(Integer declaredDiff) { this.declaredDiff = declaredDiff; }
    public Date getGmtCreate() { return gmtCreate; }
    public void setGmtCreate(Date gmtCreate) { this.gmtCreate = gmtCreate; }
    public Date getGmtModified() { return gmtModified; }
    public void setGmtModified(Date gmtModified) { this.gmtModified = gmtModified; }
    public Date getWorkingTime() { return workingTime; }
    public void setWorkingTime(Date v) { this.workingTime = v; }
    public Date getShippedTime() { return shippedTime; }
    public void setShippedTime(Date v) { this.shippedTime = v; }
    public Date getReceivingTime() { return receivingTime; }
    public void setReceivingTime(Date v) { this.receivingTime = v; }
    public Date getClosedTime() { return closedTime; }
    public void setClosedTime(Date v) { this.closedTime = v; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
    public Integer getConfirmed() { return confirmed; }
    public void setConfirmed(Integer confirmed) { this.confirmed = confirmed; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
    public String getShipToName() { return shipToName; }
    public void setShipToName(String v) { this.shipToName = v; }
    public String getShipToCountryCode() { return shipToCountryCode; }
    public void setShipToCountryCode(String v) { this.shipToCountryCode = v; }
    public String getShipToState() { return shipToState; }
    public void setShipToState(String v) { this.shipToState = v; }
    public String getShipToCity() { return shipToCity; }
    public void setShipToCity(String v) { this.shipToCity = v; }
    public String getShipToRegion() { return shipToRegion; }
    public void setShipToRegion(String v) { this.shipToRegion = v; }
    public String getShipToAddressLine1() { return shipToAddressLine1; }
    public void setShipToAddressLine1(String v) { this.shipToAddressLine1 = v; }
    public String getShipToAddressLine2() { return shipToAddressLine2; }
    public void setShipToAddressLine2(String v) { this.shipToAddressLine2 = v; }
    public String getShipToPostalCode() { return shipToPostalCode; }
    public void setShipToPostalCode(String v) { this.shipToPostalCode = v; }
    public String getShipToDoorplate() { return shipToDoorplate; }
    public void setShipToDoorplate(String v) { this.shipToDoorplate = v; }
}
