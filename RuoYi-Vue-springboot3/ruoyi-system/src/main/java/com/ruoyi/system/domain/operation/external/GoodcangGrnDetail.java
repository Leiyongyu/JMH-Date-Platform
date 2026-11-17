package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;

/**
 * 谷仓入库单明细
 */
public class GoodcangGrnDetail implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String receivingCode;
    private String productSku;
    private String boxNo;
    private Integer transitPreCount;
    private Integer transitReceivingCount;
    private String referenceBoxNo;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getReceivingCode() { return receivingCode; }
    public void setReceivingCode(String receivingCode) { this.receivingCode = receivingCode; }
    public String getProductSku() { return productSku; }
    public void setProductSku(String productSku) { this.productSku = productSku; }
    public String getBoxNo() { return boxNo; }
    public void setBoxNo(String boxNo) { this.boxNo = boxNo; }
    public Integer getTransitPreCount() { return transitPreCount; }
    public void setTransitPreCount(Integer transitPreCount) { this.transitPreCount = transitPreCount; }
    public Integer getTransitReceivingCount() { return transitReceivingCount; }
    public void setTransitReceivingCount(Integer transitReceivingCount) { this.transitReceivingCount = transitReceivingCount; }
    public String getReferenceBoxNo() { return referenceBoxNo; }
    public void setReferenceBoxNo(String referenceBoxNo) { this.referenceBoxNo = referenceBoxNo; }
}
