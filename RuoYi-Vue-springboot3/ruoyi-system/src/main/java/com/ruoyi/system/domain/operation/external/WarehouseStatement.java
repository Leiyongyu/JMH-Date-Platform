package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.util.Date;

/**
 * 仓库库存流水 (领星)
 */
public class WarehouseStatement implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String statementId;
    private Integer wid;
    private String wareHouseName;
    private String orderSn;
    private String sku;
    private Date optTime;
    private Integer type;
    private String typeText;
    private String productName;
    private Integer productGoodNum;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getStatementId() { return statementId; }
    public void setStatementId(String statementId) { this.statementId = statementId; }
    public Integer getWid() { return wid; }
    public void setWid(Integer wid) { this.wid = wid; }
    public String getWareHouseName() { return wareHouseName; }
    public void setWareHouseName(String wareHouseName) { this.wareHouseName = wareHouseName; }
    public String getOrderSn() { return orderSn; }
    public void setOrderSn(String orderSn) { this.orderSn = orderSn; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public Date getOptTime() { return optTime; }
    public void setOptTime(Date optTime) { this.optTime = optTime; }
    public Integer getType() { return type; }
    public void setType(Integer type) { this.type = type; }
    public String getTypeText() { return typeText; }
    public void setTypeText(String typeText) { this.typeText = typeText; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public Integer getProductGoodNum() { return productGoodNum; }
    public void setProductGoodNum(Integer productGoodNum) { this.productGoodNum = productGoodNum; }
}
