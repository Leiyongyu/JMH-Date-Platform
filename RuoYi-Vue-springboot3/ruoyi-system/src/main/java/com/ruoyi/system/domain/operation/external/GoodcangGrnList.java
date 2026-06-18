package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.util.Date;

/**
 * 谷仓入库单列表
 */
public class GoodcangGrnList implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String receivingCode;
    private String warehouseCode;
    private String transitWarehouseCode;
    private String referenceNo;
    private Integer receivingStatus;
    private Integer transitType;
    private Date createAt;
    private Date updateAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getReceivingCode() { return receivingCode; }
    public void setReceivingCode(String receivingCode) { this.receivingCode = receivingCode; }
    public String getWarehouseCode() { return warehouseCode; }
    public void setWarehouseCode(String warehouseCode) { this.warehouseCode = warehouseCode; }
    public String getTransitWarehouseCode() { return transitWarehouseCode; }
    public void setTransitWarehouseCode(String transitWarehouseCode) { this.transitWarehouseCode = transitWarehouseCode; }
    public String getReferenceNo() { return referenceNo; }
    public void setReferenceNo(String referenceNo) { this.referenceNo = referenceNo; }
    public Integer getReceivingStatus() { return receivingStatus; }
    public void setReceivingStatus(Integer receivingStatus) { this.receivingStatus = receivingStatus; }
    public Integer getTransitType() { return transitType; }
    public void setTransitType(Integer transitType) { this.transitType = transitType; }
    public Date getCreateAt() { return createAt; }
    public void setCreateAt(Date createAt) { this.createAt = createAt; }
    public Date getUpdateAt() { return updateAt; }
    public void setUpdateAt(Date updateAt) { this.updateAt = updateAt; }
}
