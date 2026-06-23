package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;

public class AmzProductListing implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private Integer sid;
    private String marketplace;
    private String sellerSku;
    private String asin;
    private String localSku;
    private String localName;
    private Integer status;
    private Integer reviewNum;
    private String lastStar;
    private String principalName;
    private String tagName;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Integer getSid() { return sid; }
    public void setSid(Integer sid) { this.sid = sid; }
    public String getMarketplace() { return marketplace; }
    public void setMarketplace(String marketplace) { this.marketplace = marketplace; }
    public String getSellerSku() { return sellerSku; }
    public void setSellerSku(String sellerSku) { this.sellerSku = sellerSku; }
    public String getAsin() { return asin; }
    public void setAsin(String asin) { this.asin = asin; }
    public String getLocalSku() { return localSku; }
    public void setLocalSku(String localSku) { this.localSku = localSku; }
    public String getLocalName() { return localName; }
    public void setLocalName(String localName) { this.localName = localName; }
    public Integer getStatus() { return status; }
    public void setStatus(Integer status) { this.status = status; }
    public Integer getReviewNum() { return reviewNum; }
    public void setReviewNum(Integer reviewNum) { this.reviewNum = reviewNum; }
    public String getLastStar() { return lastStar; }
    public void setLastStar(String lastStar) { this.lastStar = lastStar; }
    public String getPrincipalName() { return principalName; }
    public void setPrincipalName(String principalName) { this.principalName = principalName; }
    public String getTagName() { return tagName; }
    public void setTagName(String tagName) { this.tagName = tagName; }
}
