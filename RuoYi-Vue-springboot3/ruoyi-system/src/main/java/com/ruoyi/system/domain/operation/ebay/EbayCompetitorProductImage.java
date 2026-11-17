package com.ruoyi.system.domain.operation.ebay;

import java.io.Serializable;
import java.util.Date;

/** eBay选竞品商品本地图片。 */
public class EbayCompetitorProductImage implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private Long productId;
    private Integer sortNo;
    private String localImageUrl;
    private Date createTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getProductId() { return productId; }
    public void setProductId(Long productId) { this.productId = productId; }
    public Integer getSortNo() { return sortNo; }
    public void setSortNo(Integer sortNo) { this.sortNo = sortNo; }
    public String getLocalImageUrl() { return localImageUrl; }
    public void setLocalImageUrl(String localImageUrl) { this.localImageUrl = localImageUrl; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
}
