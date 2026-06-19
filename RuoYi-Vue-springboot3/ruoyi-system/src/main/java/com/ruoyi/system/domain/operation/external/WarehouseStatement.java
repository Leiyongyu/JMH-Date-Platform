package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.util.Date;

/** 仓库库存流水 (领星) */
public class WarehouseStatement implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private String statementId;
    private Integer wid;
    private String wareHouseName;
    private String orderSn;
    private String refOrderSn;
    private String sku;
    private Date optTime;
    private Integer type;
    private String typeText;
    private String subType;
    private String subTypeText;
    private String sellerId;
    private String fnsku;
    private String productName;
    private Integer productGoodNum;
    private Integer productBadNum;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getStatementId() { return statementId; }
    public void setStatementId(String v) { this.statementId = v; }
    public Integer getWid() { return wid; }
    public void setWid(Integer v) { this.wid = v; }
    public String getWareHouseName() { return wareHouseName; }
    public void setWareHouseName(String v) { this.wareHouseName = v; }
    public String getOrderSn() { return orderSn; }
    public void setOrderSn(String v) { this.orderSn = v; }
    public String getRefOrderSn() { return refOrderSn; }
    public void setRefOrderSn(String v) { this.refOrderSn = v; }
    public String getSku() { return sku; }
    public void setSku(String v) { this.sku = v; }
    public Date getOptTime() { return optTime; }
    public void setOptTime(Date v) { this.optTime = v; }
    public Integer getType() { return type; }
    public void setType(Integer v) { this.type = v; }
    public String getTypeText() { return typeText; }
    public void setTypeText(String v) { this.typeText = v; }
    public String getSubType() { return subType; }
    public void setSubType(String v) { this.subType = v; }
    public String getSubTypeText() { return subTypeText; }
    public void setSubTypeText(String v) { this.subTypeText = v; }
    public String getSellerId() { return sellerId; }
    public void setSellerId(String v) { this.sellerId = v; }
    public String getFnsku() { return fnsku; }
    public void setFnsku(String v) { this.fnsku = v; }
    public String getProductName() { return productName; }
    public void setProductName(String v) { this.productName = v; }
    public Integer getProductGoodNum() { return productGoodNum; }
    public void setProductGoodNum(Integer v) { this.productGoodNum = v; }
    public Integer getProductBadNum() { return productBadNum; }
    public void setProductBadNum(Integer v) { this.productBadNum = v; }
}
