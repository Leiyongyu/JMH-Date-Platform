package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

/** 采购单 (领星) */
public class PurchaseOrder implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private String orderSn;
    private String customOrderSn;
    private Integer supplierId;
    private String supplierName;
    private Integer optUid;
    private String optRealname;
    private String auditorRealname;
    private String lastRealname;
    private Integer status;
    private String statusText;
    private Integer wid;
    private String wareHouseName;
    private String itemSku;
    private String itemProductName;
    private Integer itemProductId;
    private Integer itemQuantityReal;
    private Integer itemQuantityEntry;
    private Integer itemQuantityReceive;
    private BigDecimal itemPrice;
    private BigDecimal itemAmount;
    private Date orderTime;
    private Date updateTime;
    private Date createTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getOrderSn() { return orderSn; }
    public void setOrderSn(String v) { this.orderSn = v; }
    public String getCustomOrderSn() { return customOrderSn; }
    public void setCustomOrderSn(String v) { this.customOrderSn = v; }
    public Integer getSupplierId() { return supplierId; }
    public void setSupplierId(Integer v) { this.supplierId = v; }
    public String getSupplierName() { return supplierName; }
    public void setSupplierName(String v) { this.supplierName = v; }
    public Integer getOptUid() { return optUid; }
    public void setOptUid(Integer v) { this.optUid = v; }
    public String getOptRealname() { return optRealname; }
    public void setOptRealname(String v) { this.optRealname = v; }
    public String getAuditorRealname() { return auditorRealname; }
    public void setAuditorRealname(String v) { this.auditorRealname = v; }
    public String getLastRealname() { return lastRealname; }
    public void setLastRealname(String v) { this.lastRealname = v; }
    public Integer getStatus() { return status; }
    public void setStatus(Integer v) { this.status = v; }
    public String getStatusText() { return statusText; }
    public void setStatusText(String v) { this.statusText = v; }
    public Integer getWid() { return wid; }
    public void setWid(Integer v) { this.wid = v; }
    public String getWareHouseName() { return wareHouseName; }
    public void setWareHouseName(String v) { this.wareHouseName = v; }
    public String getItemSku() { return itemSku; }
    public void setItemSku(String v) { this.itemSku = v; }
    public String getItemProductName() { return itemProductName; }
    public void setItemProductName(String v) { this.itemProductName = v; }
    public Integer getItemProductId() { return itemProductId; }
    public void setItemProductId(Integer v) { this.itemProductId = v; }
    public Integer getItemQuantityReal() { return itemQuantityReal; }
    public void setItemQuantityReal(Integer v) { this.itemQuantityReal = v; }
    public Integer getItemQuantityEntry() { return itemQuantityEntry; }
    public void setItemQuantityEntry(Integer v) { this.itemQuantityEntry = v; }
    public Integer getItemQuantityReceive() { return itemQuantityReceive; }
    public void setItemQuantityReceive(Integer v) { this.itemQuantityReceive = v; }
    public BigDecimal getItemPrice() { return itemPrice; }
    public void setItemPrice(BigDecimal v) { this.itemPrice = v; }
    public BigDecimal getItemAmount() { return itemAmount; }
    public void setItemAmount(BigDecimal v) { this.itemAmount = v; }
    public Date getOrderTime() { return orderTime; }
    public void setOrderTime(Date v) { this.orderTime = v; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date v) { this.updateTime = v; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date v) { this.createTime = v; }
}
