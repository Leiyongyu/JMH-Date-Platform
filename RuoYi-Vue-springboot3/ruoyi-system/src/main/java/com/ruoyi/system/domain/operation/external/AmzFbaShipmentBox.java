package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.util.Date;

/** Amazon FBA 货件装箱信息 */
public class AmzFbaShipmentBox implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private Integer sid;
    private String shipmentId;
    private String boxType;
    private String boxLength;
    private String boxWidth;
    private String boxHeight;
    private String boxWeight;
    private String boxDimensionsUnit;
    private String boxWeightUnit;
    private Integer boxNum;
    private String msku;
    private String sku;
    private String fulfillmentNetworkSku;
    private String quantityInCase;
    private Date createTime;

    public Long getId() { return id; }
    public void setId(Long v) { this.id = v; }
    public Integer getSid() { return sid; }
    public void setSid(Integer v) { this.sid = v; }
    public String getShipmentId() { return shipmentId; }
    public void setShipmentId(String v) { this.shipmentId = v; }
    public String getBoxType() { return boxType; }
    public void setBoxType(String v) { this.boxType = v; }
    public String getBoxLength() { return boxLength; }
    public void setBoxLength(String v) { this.boxLength = v; }
    public String getBoxWidth() { return boxWidth; }
    public void setBoxWidth(String v) { this.boxWidth = v; }
    public String getBoxHeight() { return boxHeight; }
    public void setBoxHeight(String v) { this.boxHeight = v; }
    public String getBoxWeight() { return boxWeight; }
    public void setBoxWeight(String v) { this.boxWeight = v; }
    public String getBoxDimensionsUnit() { return boxDimensionsUnit; }
    public void setBoxDimensionsUnit(String v) { this.boxDimensionsUnit = v; }
    public String getBoxWeightUnit() { return boxWeightUnit; }
    public void setBoxWeightUnit(String v) { this.boxWeightUnit = v; }
    public Integer getBoxNum() { return boxNum; }
    public void setBoxNum(Integer v) { this.boxNum = v; }
    public String getMsku() { return msku; }
    public void setMsku(String v) { this.msku = v; }
    public String getSku() { return sku; }
    public void setSku(String v) { this.sku = v; }
    public String getFulfillmentNetworkSku() { return fulfillmentNetworkSku; }
    public void setFulfillmentNetworkSku(String v) { this.fulfillmentNetworkSku = v; }
    public String getQuantityInCase() { return quantityInCase; }
    public void setQuantityInCase(String v) { this.quantityInCase = v; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date v) { this.createTime = v; }
}
