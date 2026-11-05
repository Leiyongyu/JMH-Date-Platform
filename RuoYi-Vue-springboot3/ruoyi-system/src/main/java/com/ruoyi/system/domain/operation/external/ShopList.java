package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 多平台店铺表 (shop_list)。统一存 eBay/Amazon 店铺信息。
 *
 * @author JMH
 */
public class ShopList implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String storeId;
    private String sid;
    private String storeName;
    private String platformCode;
    private String platformName;
    private String currency;
    private Integer isSync;
    private Integer status;
    private String countryCode;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    /** 拉取控制（店铺管理页面维护，领星店铺同步不覆盖）：1 拉取，0 停止拉取（历史数据保留） */
    private Integer pullEnabled;
    private String pullStopReason;
    /** 停止拉取生效日期：按月拉取的任务，开始于该日期之前的月份仍会拉取，避免重跑历史月份时丢数据 */
    private java.time.LocalDate pullStopDate;
    private String pullUpdatedBy;
    private LocalDateTime pullUpdatedAt;
    /** 最近一次完整的领星店铺同步是否返回了该店铺：0 表示领星已移除，自动不再拉取 */
    private Integer lingxingPresent;
    private LocalDateTime lingxingLastSeenAt;

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

    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }

    public Integer getIsSync() { return isSync; }
    public void setIsSync(Integer isSync) { this.isSync = isSync; }

    public Integer getStatus() { return status; }
    public void setStatus(Integer status) { this.status = status; }

    public String getCountryCode() { return countryCode; }
    public void setCountryCode(String countryCode) { this.countryCode = countryCode; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }

    public Integer getPullEnabled() { return pullEnabled; }
    public void setPullEnabled(Integer pullEnabled) { this.pullEnabled = pullEnabled; }

    public String getPullStopReason() { return pullStopReason; }
    public void setPullStopReason(String pullStopReason) { this.pullStopReason = pullStopReason; }

    public java.time.LocalDate getPullStopDate() { return pullStopDate; }
    public void setPullStopDate(java.time.LocalDate pullStopDate) { this.pullStopDate = pullStopDate; }

    public String getPullUpdatedBy() { return pullUpdatedBy; }
    public void setPullUpdatedBy(String pullUpdatedBy) { this.pullUpdatedBy = pullUpdatedBy; }

    public LocalDateTime getPullUpdatedAt() { return pullUpdatedAt; }
    public void setPullUpdatedAt(LocalDateTime pullUpdatedAt) { this.pullUpdatedAt = pullUpdatedAt; }

    public Integer getLingxingPresent() { return lingxingPresent; }
    public void setLingxingPresent(Integer lingxingPresent) { this.lingxingPresent = lingxingPresent; }

    public LocalDateTime getLingxingLastSeenAt() { return lingxingLastSeenAt; }
    public void setLingxingLastSeenAt(LocalDateTime lingxingLastSeenAt) { this.lingxingLastSeenAt = lingxingLastSeenAt; }
}
