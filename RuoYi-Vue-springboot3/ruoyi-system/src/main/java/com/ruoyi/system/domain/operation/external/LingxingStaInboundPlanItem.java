package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.time.LocalDateTime;

/** 领星STA任务商品明细。 */
public class LingxingStaInboundPlanItem implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String recordKey;
    private String inboundPlanId;
    private Integer itemIndex;
    private String asin;
    private String fnsku;
    private String msku;
    private String parentAsin;
    private String productName;
    private Integer quantity;
    private String sku;
    private String title;
    private String url;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getRecordKey() { return recordKey; }
    public void setRecordKey(String recordKey) { this.recordKey = recordKey; }
    public String getInboundPlanId() { return inboundPlanId; }
    public void setInboundPlanId(String inboundPlanId) { this.inboundPlanId = inboundPlanId; }
    public Integer getItemIndex() { return itemIndex; }
    public void setItemIndex(Integer itemIndex) { this.itemIndex = itemIndex; }
    public String getAsin() { return asin; }
    public void setAsin(String asin) { this.asin = asin; }
    public String getFnsku() { return fnsku; }
    public void setFnsku(String fnsku) { this.fnsku = fnsku; }
    public String getMsku() { return msku; }
    public void setMsku(String msku) { this.msku = msku; }
    public String getParentAsin() { return parentAsin; }
    public void setParentAsin(String parentAsin) { this.parentAsin = parentAsin; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getUrl() { return url; }
    public void setUrl(String url) { this.url = url; }
    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
    public LocalDateTime getUpdateTime() { return updateTime; }
    public void setUpdateTime(LocalDateTime updateTime) { this.updateTime = updateTime; }
}
