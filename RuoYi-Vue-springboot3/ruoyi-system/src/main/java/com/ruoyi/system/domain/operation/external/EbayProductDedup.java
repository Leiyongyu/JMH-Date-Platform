package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

/**
 * eBay商品去重表
 */
public class EbayProductDedup implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String site;
    private String sku;
    private String oeNumber;
    private String productName;
    private BigDecimal trackingPrice;
    private BigDecimal trackingProfitMargin;
    private BigDecimal floorPrice;
    private String remark;
    private BigDecimal profitRate;
    private BigDecimal returnRate;
    private BigDecimal lowestPrice;
    private String lowestItemNumber;
    private Date lowestUploadTime;
    private Date createTime;
    private Date updateTime;
    private Integer productNature;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSite() { return site; }
    public void setSite(String site) { this.site = site; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getOeNumber() { return oeNumber; }
    public void setOeNumber(String oeNumber) { this.oeNumber = oeNumber; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public BigDecimal getTrackingPrice() { return trackingPrice; }
    public void setTrackingPrice(BigDecimal trackingPrice) { this.trackingPrice = trackingPrice; }
    public BigDecimal getTrackingProfitMargin() { return trackingProfitMargin; }
    public void setTrackingProfitMargin(BigDecimal trackingProfitMargin) { this.trackingProfitMargin = trackingProfitMargin; }
    public BigDecimal getFloorPrice() { return floorPrice; }
    public void setFloorPrice(BigDecimal floorPrice) { this.floorPrice = floorPrice; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
    public BigDecimal getProfitRate() { return profitRate; }
    public void setProfitRate(BigDecimal profitRate) { this.profitRate = profitRate; }
    public BigDecimal getReturnRate() { return returnRate; }
    public void setReturnRate(BigDecimal returnRate) { this.returnRate = returnRate; }
    public BigDecimal getLowestPrice() { return lowestPrice; }
    public void setLowestPrice(BigDecimal lowestPrice) { this.lowestPrice = lowestPrice; }
    public String getLowestItemNumber() { return lowestItemNumber; }
    public void setLowestItemNumber(String lowestItemNumber) { this.lowestItemNumber = lowestItemNumber; }
    public Date getLowestUploadTime() { return lowestUploadTime; }
    public void setLowestUploadTime(Date lowestUploadTime) { this.lowestUploadTime = lowestUploadTime; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date updateTime) { this.updateTime = updateTime; }
    public Integer getProductNature() { return productNature; }
    public void setProductNature(Integer v) { this.productNature = v; }
}
