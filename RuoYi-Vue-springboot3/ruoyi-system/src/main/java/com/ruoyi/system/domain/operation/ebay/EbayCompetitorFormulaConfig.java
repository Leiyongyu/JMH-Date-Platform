package com.ruoyi.system.domain.operation.ebay;

import java.math.BigDecimal;

/** eBay选竞品站点公式配置。 */
public class EbayCompetitorFormulaConfig
{
    private String siteCode;
    private String siteName;
    private String currency;
    private BigDecimal platformNetRate;
    private BigDecimal volumetricDivisor;
    private BigDecimal fixedFee;
    private BigDecimal weightHandlingRate;
    private BigDecimal seaFirstLegRate;
    private BigDecimal profitFirstLegRate;
    private BigDecimal targetCostFirstLegRate;
    private BigDecimal railFirstLegRate;
    private BigDecimal smallWeightThreshold;
    private BigDecimal smallFixedFee;
    private BigDecimal largeFixedFee;
    private BigDecimal smallDeliveryRate;
    private BigDecimal largeDeliveryRate;
    private BigDecimal chargeableVolumeFactor;
    private String formulaVersion;
    private String status;

    public String getSiteCode() { return siteCode; }
    public void setSiteCode(String siteCode) { this.siteCode = siteCode; }
    public String getSiteName() { return siteName; }
    public void setSiteName(String siteName) { this.siteName = siteName; }
    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }
    public BigDecimal getPlatformNetRate() { return platformNetRate; }
    public void setPlatformNetRate(BigDecimal platformNetRate) { this.platformNetRate = platformNetRate; }
    public BigDecimal getVolumetricDivisor() { return volumetricDivisor; }
    public void setVolumetricDivisor(BigDecimal volumetricDivisor) { this.volumetricDivisor = volumetricDivisor; }
    public BigDecimal getFixedFee() { return fixedFee; }
    public void setFixedFee(BigDecimal fixedFee) { this.fixedFee = fixedFee; }
    public BigDecimal getWeightHandlingRate() { return weightHandlingRate; }
    public void setWeightHandlingRate(BigDecimal weightHandlingRate) { this.weightHandlingRate = weightHandlingRate; }
    public BigDecimal getSeaFirstLegRate() { return seaFirstLegRate; }
    public void setSeaFirstLegRate(BigDecimal seaFirstLegRate) { this.seaFirstLegRate = seaFirstLegRate; }
    public BigDecimal getProfitFirstLegRate() { return profitFirstLegRate; }
    public void setProfitFirstLegRate(BigDecimal profitFirstLegRate) { this.profitFirstLegRate = profitFirstLegRate; }
    public BigDecimal getTargetCostFirstLegRate() { return targetCostFirstLegRate; }
    public void setTargetCostFirstLegRate(BigDecimal targetCostFirstLegRate) { this.targetCostFirstLegRate = targetCostFirstLegRate; }
    public BigDecimal getRailFirstLegRate() { return railFirstLegRate; }
    public void setRailFirstLegRate(BigDecimal railFirstLegRate) { this.railFirstLegRate = railFirstLegRate; }
    public BigDecimal getSmallWeightThreshold() { return smallWeightThreshold; }
    public void setSmallWeightThreshold(BigDecimal smallWeightThreshold) { this.smallWeightThreshold = smallWeightThreshold; }
    public BigDecimal getSmallFixedFee() { return smallFixedFee; }
    public void setSmallFixedFee(BigDecimal smallFixedFee) { this.smallFixedFee = smallFixedFee; }
    public BigDecimal getLargeFixedFee() { return largeFixedFee; }
    public void setLargeFixedFee(BigDecimal largeFixedFee) { this.largeFixedFee = largeFixedFee; }
    public BigDecimal getSmallDeliveryRate() { return smallDeliveryRate; }
    public void setSmallDeliveryRate(BigDecimal smallDeliveryRate) { this.smallDeliveryRate = smallDeliveryRate; }
    public BigDecimal getLargeDeliveryRate() { return largeDeliveryRate; }
    public void setLargeDeliveryRate(BigDecimal largeDeliveryRate) { this.largeDeliveryRate = largeDeliveryRate; }
    public BigDecimal getChargeableVolumeFactor() { return chargeableVolumeFactor; }
    public void setChargeableVolumeFactor(BigDecimal chargeableVolumeFactor) { this.chargeableVolumeFactor = chargeableVolumeFactor; }
    public String getFormulaVersion() { return formulaVersion; }
    public void setFormulaVersion(String formulaVersion) { this.formulaVersion = formulaVersion; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
}
