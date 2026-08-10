package com.ruoyi.system.domain.operation.ebay;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

/**
 * eBay Browse API 商品详情，字段保持与原 Python 接口一致。
 */
public class EbayItemDetail
{
    private String oe;
    private String title;
    private String price;
    private BigDecimal pf = BigDecimal.ZERO;
    private String currency;
    private Integer estimatedSoldQuantity;
    private String condition;
    private String conditionId;
    private List<String> images = new ArrayList<>();
    private String link;
    private String itemId;
    private String productId;
    private String seller;
    private String sellerFeedback;
    private String shipping;
    private List<String> buyingOptions = new ArrayList<>();
    private boolean imageDetailComplete;
    private String imageDetailError;

    public String getOe() { return oe; }
    public void setOe(String oe) { this.oe = oe; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getPrice() { return price; }
    public void setPrice(String price) { this.price = price; }
    public BigDecimal getPf() { return pf; }
    public void setPf(BigDecimal pf) { this.pf = pf == null ? BigDecimal.ZERO : pf; }
    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }
    public Integer getEstimatedSoldQuantity() { return estimatedSoldQuantity; }
    public void setEstimatedSoldQuantity(Integer estimatedSoldQuantity) { this.estimatedSoldQuantity = estimatedSoldQuantity; }
    public String getCondition() { return condition; }
    public void setCondition(String condition) { this.condition = condition; }
    public String getConditionId() { return conditionId; }
    public void setConditionId(String conditionId) { this.conditionId = conditionId; }
    public List<String> getImages() { return images; }
    public void setImages(List<String> images) { this.images = images == null ? new ArrayList<>() : images; }
    public String getLink() { return link; }
    public void setLink(String link) { this.link = link; }
    public String getItemId() { return itemId; }
    public void setItemId(String itemId) { this.itemId = itemId; }
    public String getProductId() { return productId; }
    public void setProductId(String productId) { this.productId = productId; }
    public String getSeller() { return seller; }
    public void setSeller(String seller) { this.seller = seller; }
    public String getSellerFeedback() { return sellerFeedback; }
    public void setSellerFeedback(String sellerFeedback) { this.sellerFeedback = sellerFeedback; }
    public String getShipping() { return shipping; }
    public void setShipping(String shipping) { this.shipping = shipping; }
    public List<String> getBuyingOptions() { return buyingOptions; }
    public void setBuyingOptions(List<String> buyingOptions) { this.buyingOptions = buyingOptions == null ? new ArrayList<>() : buyingOptions; }
    public boolean isImageDetailComplete() { return imageDetailComplete; }
    public void setImageDetailComplete(boolean imageDetailComplete) { this.imageDetailComplete = imageDetailComplete; }
    public String getImageDetailError() { return imageDetailError; }
    public void setImageDetailError(String imageDetailError) { this.imageDetailError = imageDetailError; }
}
