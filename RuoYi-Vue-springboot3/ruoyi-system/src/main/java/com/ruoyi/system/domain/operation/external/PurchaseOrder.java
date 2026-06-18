package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

/**
 * 采购单(全字段) (领星)
 */
public class PurchaseOrder implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String orderSn;
    private String supplierName;
    private String statusText;
    private Integer wid;
    private String wareHouseName;
    private String itemSku;
    private String itemProductName;
    private Date orderTime;
    private Date createTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getOrderSn() { return orderSn; }
    public void setOrderSn(String orderSn) { this.orderSn = orderSn; }
    public String getSupplierName() { return supplierName; }
    public void setSupplierName(String supplierName) { this.supplierName = supplierName; }
    public String getStatusText() { return statusText; }
    public void setStatusText(String statusText) { this.statusText = statusText; }
    public Integer getWid() { return wid; }
    public void setWid(Integer wid) { this.wid = wid; }
    public String getWareHouseName() { return wareHouseName; }
    public void setWareHouseName(String wareHouseName) { this.wareHouseName = wareHouseName; }
    public String getItemSku() { return itemSku; }
    public void setItemSku(String itemSku) { this.itemSku = itemSku; }
    public String getItemProductName() { return itemProductName; }
    public void setItemProductName(String itemProductName) { this.itemProductName = itemProductName; }
    public Date getOrderTime() { return orderTime; }
    public void setOrderTime(Date orderTime) { this.orderTime = orderTime; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
}
