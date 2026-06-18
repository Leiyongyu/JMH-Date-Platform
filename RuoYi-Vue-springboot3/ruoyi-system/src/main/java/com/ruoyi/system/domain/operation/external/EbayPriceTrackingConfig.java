package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

/**
 * eBay跟价用户可编辑配置表 —— 与快照表分离，避免刷新覆盖手动维护字段。
 */
public class EbayPriceTrackingConfig implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String site;
    private String sku;
    private String oeNumber;
    private String remark;
    private BigDecimal trackingPrice;
    private BigDecimal trackingProfitMargin;
    private BigDecimal floorPrice;
    private BigDecimal ourLowestPrice;
    private Integer version;
    private Date createTime;
    private Date updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSite() { return site; }
    public void setSite(String site) { this.site = site; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getOeNumber() { return oeNumber; }
    public void setOeNumber(String oeNumber) { this.oeNumber = oeNumber; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
    public BigDecimal getTrackingPrice() { return trackingPrice; }
    public void setTrackingPrice(BigDecimal trackingPrice) { this.trackingPrice = trackingPrice; }
    public BigDecimal getTrackingProfitMargin() { return trackingProfitMargin; }
    public void setTrackingProfitMargin(BigDecimal trackingProfitMargin) { this.trackingProfitMargin = trackingProfitMargin; }
    public BigDecimal getFloorPrice() { return floorPrice; }
    public void setFloorPrice(BigDecimal floorPrice) { this.floorPrice = floorPrice; }
    public BigDecimal getOurLowestPrice() { return ourLowestPrice; }
    public void setOurLowestPrice(BigDecimal ourLowestPrice) { this.ourLowestPrice = ourLowestPrice; }
    public Integer getVersion() { return version; }
    public void setVersion(Integer version) { this.version = version; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date updateTime) { this.updateTime = updateTime; }
}
