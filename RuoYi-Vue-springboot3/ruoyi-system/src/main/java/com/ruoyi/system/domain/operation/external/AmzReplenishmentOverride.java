package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

public class AmzReplenishmentOverride implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private String sid;
    private String sellerSku;
    private BigDecimal manualPurchasedQty;
    private String productCategory;
    private String remark;
    private Date createTime;
    private Date updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSid() { return sid; }
    public void setSid(String sid) { this.sid = sid; }
    public String getSellerSku() { return sellerSku; }
    public void setSellerSku(String sellerSku) { this.sellerSku = sellerSku; }
    public BigDecimal getManualPurchasedQty() { return manualPurchasedQty; }
    public void setManualPurchasedQty(BigDecimal manualPurchasedQty) { this.manualPurchasedQty = manualPurchasedQty; }
    public String getProductCategory() { return productCategory; }
    public void setProductCategory(String productCategory) { this.productCategory = productCategory; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date updateTime) { this.updateTime = updateTime; }
}
