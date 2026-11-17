package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;

public class AmzWarehouseInventoryDetail implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private Integer wid;
    private String sellerId;
    private String sku;
    private BigDecimal quantityReceive;
    private Integer productValidNum;
    private Integer productLockNum;
    private Integer productQcNum;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Integer getWid() { return wid; }
    public void setWid(Integer wid) { this.wid = wid; }
    public String getSellerId() { return sellerId; }
    public void setSellerId(String sellerId) { this.sellerId = sellerId; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public BigDecimal getQuantityReceive() { return quantityReceive; }
    public void setQuantityReceive(BigDecimal quantityReceive) { this.quantityReceive = quantityReceive; }
    public Integer getProductValidNum() { return productValidNum; }
    public void setProductValidNum(Integer productValidNum) { this.productValidNum = productValidNum; }
    public Integer getProductLockNum() { return productLockNum; }
    public void setProductLockNum(Integer productLockNum) { this.productLockNum = productLockNum; }
    public Integer getProductQcNum() { return productQcNum; }
    public void setProductQcNum(Integer productQcNum) { this.productQcNum = productQcNum; }
}
