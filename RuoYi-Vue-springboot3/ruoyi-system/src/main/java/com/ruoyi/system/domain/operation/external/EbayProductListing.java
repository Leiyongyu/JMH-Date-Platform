package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * eBay 商品刊登源数据表 ebay_product_listing。
 */
public class EbayProductListing implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private String platform;
    private String itemId;
    private String itemUrl;
    private String pictureUrl;
    private String msku;
    private String sku;
    private String localSku;
    private String title;
    private String localName;
    private String attribute;
    private Integer listingType;
    private String listingTypeName;
    private Integer listingStatus;
    private String listingStatusName;
    private BigDecimal price;
    private BigDecimal startPrice;
    private BigDecimal acceptPrice;
    private Integer quantity;
    private Integer autoRestock;
    private String productAutoRestockResponse;
    private String location;
    private Integer dispatchTimeMax;
    private LocalDateTime listingStartTime;
    private LocalDateTime listingEndTime;
    private String storeId;
    private String storeName;
    private String siteCode;
    private String siteName;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    // getters/setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getPlatform() { return platform; }
    public void setPlatform(String platform) { this.platform = platform; }
    public String getItemId() { return itemId; }
    public void setItemId(String itemId) { this.itemId = itemId; }
    public String getItemUrl() { return itemUrl; }
    public void setItemUrl(String itemUrl) { this.itemUrl = itemUrl; }
    public String getPictureUrl() { return pictureUrl; }
    public void setPictureUrl(String pictureUrl) { this.pictureUrl = pictureUrl; }
    public String getMsku() { return msku; }
    public void setMsku(String msku) { this.msku = msku; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getLocalSku() { return localSku; }
    public void setLocalSku(String localSku) { this.localSku = localSku; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getLocalName() { return localName; }
    public void setLocalName(String localName) { this.localName = localName; }
    public String getAttribute() { return attribute; }
    public void setAttribute(String attribute) { this.attribute = attribute; }
    public Integer getListingType() { return listingType; }
    public void setListingType(Integer listingType) { this.listingType = listingType; }
    public String getListingTypeName() { return listingTypeName; }
    public void setListingTypeName(String listingTypeName) { this.listingTypeName = listingTypeName; }
    public Integer getListingStatus() { return listingStatus; }
    public void setListingStatus(Integer listingStatus) { this.listingStatus = listingStatus; }
    public String getListingStatusName() { return listingStatusName; }
    public void setListingStatusName(String listingStatusName) { this.listingStatusName = listingStatusName; }
    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }
    public BigDecimal getStartPrice() { return startPrice; }
    public void setStartPrice(BigDecimal startPrice) { this.startPrice = startPrice; }
    public BigDecimal getAcceptPrice() { return acceptPrice; }
    public void setAcceptPrice(BigDecimal acceptPrice) { this.acceptPrice = acceptPrice; }
    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
    public Integer getAutoRestock() { return autoRestock; }
    public void setAutoRestock(Integer autoRestock) { this.autoRestock = autoRestock; }
    public String getProductAutoRestockResponse() { return productAutoRestockResponse; }
    public void setProductAutoRestockResponse(String v) { this.productAutoRestockResponse = v; }
    public String getLocation() { return location; }
    public void setLocation(String location) { this.location = location; }
    public Integer getDispatchTimeMax() { return dispatchTimeMax; }
    public void setDispatchTimeMax(Integer dispatchTimeMax) { this.dispatchTimeMax = dispatchTimeMax; }
    public LocalDateTime getListingStartTime() { return listingStartTime; }
    public void setListingStartTime(LocalDateTime t) { this.listingStartTime = t; }
    public LocalDateTime getListingEndTime() { return listingEndTime; }
    public void setListingEndTime(LocalDateTime t) { this.listingEndTime = t; }
    public String getStoreId() { return storeId; }
    public void setStoreId(String storeId) { this.storeId = storeId; }
    public String getStoreName() { return storeName; }
    public void setStoreName(String storeName) { this.storeName = storeName; }
    public String getSiteCode() { return siteCode; }
    public void setSiteCode(String siteCode) { this.siteCode = siteCode; }
    public String getSiteName() { return siteName; }
    public void setSiteName(String siteName) { this.siteName = siteName; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime t) { this.createdAt = t; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime t) { this.updatedAt = t; }
}
