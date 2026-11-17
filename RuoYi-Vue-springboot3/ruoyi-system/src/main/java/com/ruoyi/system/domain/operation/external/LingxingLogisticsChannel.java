package com.ruoyi.system.domain.operation.external;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/** 领星头程物流渠道。 */
public class LingxingLogisticsChannel
{
    private Long id;
    private String channelName;
    private String methodId;
    private String methodName;
    private Integer billingType;
    private String volumeCalcParam;
    private String zipCode;
    private Integer validPeriod;
    private String remark;
    private Integer enabled;
    private Long lastModifyUid;
    private LocalDateTime gmtModified;
    private String providerId;
    private String providerName;
    private String freightJson;
    private String sendPlaceCode;
    private String receiveCountryCode;
    private Integer isIncludeTax;
    private Integer isPointsBehind;
    private BigDecimal pointsBehindCoefficient;
    private String rawJson;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getChannelName() { return channelName; }
    public void setChannelName(String channelName) { this.channelName = channelName; }
    public String getMethodId() { return methodId; }
    public void setMethodId(String methodId) { this.methodId = methodId; }
    public String getMethodName() { return methodName; }
    public void setMethodName(String methodName) { this.methodName = methodName; }
    public Integer getBillingType() { return billingType; }
    public void setBillingType(Integer billingType) { this.billingType = billingType; }
    public String getVolumeCalcParam() { return volumeCalcParam; }
    public void setVolumeCalcParam(String volumeCalcParam) { this.volumeCalcParam = volumeCalcParam; }
    public String getZipCode() { return zipCode; }
    public void setZipCode(String zipCode) { this.zipCode = zipCode; }
    public Integer getValidPeriod() { return validPeriod; }
    public void setValidPeriod(Integer validPeriod) { this.validPeriod = validPeriod; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
    public Integer getEnabled() { return enabled; }
    public void setEnabled(Integer enabled) { this.enabled = enabled; }
    public Long getLastModifyUid() { return lastModifyUid; }
    public void setLastModifyUid(Long lastModifyUid) { this.lastModifyUid = lastModifyUid; }
    public LocalDateTime getGmtModified() { return gmtModified; }
    public void setGmtModified(LocalDateTime gmtModified) { this.gmtModified = gmtModified; }
    public String getProviderId() { return providerId; }
    public void setProviderId(String providerId) { this.providerId = providerId; }
    public String getProviderName() { return providerName; }
    public void setProviderName(String providerName) { this.providerName = providerName; }
    public String getFreightJson() { return freightJson; }
    public void setFreightJson(String freightJson) { this.freightJson = freightJson; }
    public String getSendPlaceCode() { return sendPlaceCode; }
    public void setSendPlaceCode(String sendPlaceCode) { this.sendPlaceCode = sendPlaceCode; }
    public String getReceiveCountryCode() { return receiveCountryCode; }
    public void setReceiveCountryCode(String receiveCountryCode) { this.receiveCountryCode = receiveCountryCode; }
    public Integer getIsIncludeTax() { return isIncludeTax; }
    public void setIsIncludeTax(Integer isIncludeTax) { this.isIncludeTax = isIncludeTax; }
    public Integer getIsPointsBehind() { return isPointsBehind; }
    public void setIsPointsBehind(Integer isPointsBehind) { this.isPointsBehind = isPointsBehind; }
    public BigDecimal getPointsBehindCoefficient() { return pointsBehindCoefficient; }
    public void setPointsBehindCoefficient(BigDecimal pointsBehindCoefficient) { this.pointsBehindCoefficient = pointsBehindCoefficient; }
    public String getRawJson() { return rawJson; }
    public void setRawJson(String rawJson) { this.rawJson = rawJson; }
    public LocalDateTime getCreateTime() { return createTime; }
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
    public LocalDateTime getUpdateTime() { return updateTime; }
    public void setUpdateTime(LocalDateTime updateTime) { this.updateTime = updateTime; }
}
