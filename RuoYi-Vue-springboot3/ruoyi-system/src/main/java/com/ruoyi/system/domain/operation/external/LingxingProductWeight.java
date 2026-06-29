package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

/** 领星产品毛重 */
public class LingxingProductWeight implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private String sku;
    private BigDecimal grossWeight;
    private Date createTime;
    private Date updateTime;

    public Long getId() { return id; }
    public void setId(Long v) { this.id = v; }
    public String getSku() { return sku; }
    public void setSku(String v) { this.sku = v; }
    public BigDecimal getGrossWeight() { return grossWeight; }
    public void setGrossWeight(BigDecimal v) { this.grossWeight = v; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date v) { this.createTime = v; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date v) { this.updateTime = v; }
}
