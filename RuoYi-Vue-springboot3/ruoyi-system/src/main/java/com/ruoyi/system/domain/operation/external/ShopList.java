package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;

public class ShopList implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private String storeId;
    private String sid;
    private String storeName;
    private String platformCode;
    private String platformName;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getStoreId() { return storeId; }
    public void setStoreId(String storeId) { this.storeId = storeId; }
    public String getSid() { return sid; }
    public void setSid(String sid) { this.sid = sid; }
    public String getStoreName() { return storeName; }
    public void setStoreName(String storeName) { this.storeName = storeName; }
    public String getPlatformCode() { return platformCode; }
    public void setPlatformCode(String platformCode) { this.platformCode = platformCode; }
    public String getPlatformName() { return platformName; }
    public void setPlatformName(String platformName) { this.platformName = platformName; }
}
