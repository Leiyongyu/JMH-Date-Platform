package com.ruoyi.system.domain.operation.ebay;

import java.math.BigDecimal;
import java.util.List;
import com.ruoyi.common.core.domain.BaseEntity;

/** eBay选竞品已保存商品。 */
public class EbayCompetitorProduct extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String siteCode;
    private String marketplaceId;
    private String currency;
    private String ebayItemId;
    private String oe;
    private String sku;
    private String referenceUrl;
    private BigDecimal salePrice;
    private BigDecimal productCostCny;
    private BigDecimal lengthCm;
    private BigDecimal widthCm;
    private BigDecimal heightCm;
    private BigDecimal volumetricWeightKg;
    private BigDecimal actualWeightKg;
    private BigDecimal exchangeRate;
    private BigDecimal seaFloorPrice;
    private BigDecimal railFloorPrice;
    private BigDecimal seaProfitRate;
    private BigDecimal railProfitRate;
    private BigDecimal targetProfitRate;
    private BigDecimal targetProductCostSea;
    private BigDecimal targetProductCostRail;
    private String localImageUrl;
    private String remoteImageUrl;
    private List<String> remoteImageUrls;
    private List<EbayCompetitorProductImage> images;
    private EbayCompetitorFormulaConfig formulaConfig;
    private String formulaVersion;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSiteCode() { return siteCode; }
    public void setSiteCode(String siteCode) { this.siteCode = siteCode; }
    public String getMarketplaceId() { return marketplaceId; }
    public void setMarketplaceId(String marketplaceId) { this.marketplaceId = marketplaceId; }
    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }
    public String getEbayItemId() { return ebayItemId; }
    public void setEbayItemId(String ebayItemId) { this.ebayItemId = ebayItemId; }
    public String getOe() { return oe; }
    public void setOe(String oe) { this.oe = oe; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getReferenceUrl() { return referenceUrl; }
    public void setReferenceUrl(String referenceUrl) { this.referenceUrl = referenceUrl; }
    public BigDecimal getSalePrice() { return salePrice; }
    public void setSalePrice(BigDecimal salePrice) { this.salePrice = salePrice; }
    public BigDecimal getProductCostCny() { return productCostCny; }
    public void setProductCostCny(BigDecimal productCostCny) { this.productCostCny = productCostCny; }
    public BigDecimal getLengthCm() { return lengthCm; }
    public void setLengthCm(BigDecimal lengthCm) { this.lengthCm = lengthCm; }
    public BigDecimal getWidthCm() { return widthCm; }
    public void setWidthCm(BigDecimal widthCm) { this.widthCm = widthCm; }
    public BigDecimal getHeightCm() { return heightCm; }
    public void setHeightCm(BigDecimal heightCm) { this.heightCm = heightCm; }
    public BigDecimal getVolumetricWeightKg() { return volumetricWeightKg; }
    public void setVolumetricWeightKg(BigDecimal volumetricWeightKg) { this.volumetricWeightKg = volumetricWeightKg; }
    public BigDecimal getActualWeightKg() { return actualWeightKg; }
    public void setActualWeightKg(BigDecimal actualWeightKg) { this.actualWeightKg = actualWeightKg; }
    public BigDecimal getExchangeRate() { return exchangeRate; }
    public void setExchangeRate(BigDecimal exchangeRate) { this.exchangeRate = exchangeRate; }
    public BigDecimal getSeaFloorPrice() { return seaFloorPrice; }
    public void setSeaFloorPrice(BigDecimal seaFloorPrice) { this.seaFloorPrice = seaFloorPrice; }
    public BigDecimal getRailFloorPrice() { return railFloorPrice; }
    public void setRailFloorPrice(BigDecimal railFloorPrice) { this.railFloorPrice = railFloorPrice; }
    public BigDecimal getSeaProfitRate() { return seaProfitRate; }
    public void setSeaProfitRate(BigDecimal seaProfitRate) { this.seaProfitRate = seaProfitRate; }
    public BigDecimal getRailProfitRate() { return railProfitRate; }
    public void setRailProfitRate(BigDecimal railProfitRate) { this.railProfitRate = railProfitRate; }
    public BigDecimal getTargetProfitRate() { return targetProfitRate; }
    public void setTargetProfitRate(BigDecimal targetProfitRate) { this.targetProfitRate = targetProfitRate; }
    public BigDecimal getTargetProductCostSea() { return targetProductCostSea; }
    public void setTargetProductCostSea(BigDecimal targetProductCostSea) { this.targetProductCostSea = targetProductCostSea; }
    public BigDecimal getTargetProductCostRail() { return targetProductCostRail; }
    public void setTargetProductCostRail(BigDecimal targetProductCostRail) { this.targetProductCostRail = targetProductCostRail; }
    public String getLocalImageUrl() { return localImageUrl; }
    public void setLocalImageUrl(String localImageUrl) { this.localImageUrl = localImageUrl; }
    public String getRemoteImageUrl() { return remoteImageUrl; }
    public void setRemoteImageUrl(String remoteImageUrl) { this.remoteImageUrl = remoteImageUrl; }
    public List<String> getRemoteImageUrls() { return remoteImageUrls; }
    public void setRemoteImageUrls(List<String> remoteImageUrls) { this.remoteImageUrls = remoteImageUrls; }
    public List<EbayCompetitorProductImage> getImages() { return images; }
    public void setImages(List<EbayCompetitorProductImage> images) { this.images = images; }
    public EbayCompetitorFormulaConfig getFormulaConfig() { return formulaConfig; }
    public void setFormulaConfig(EbayCompetitorFormulaConfig formulaConfig) { this.formulaConfig = formulaConfig; }
    public String getFormulaVersion() { return formulaVersion; }
    public void setFormulaVersion(String formulaVersion) { this.formulaVersion = formulaVersion; }
}
