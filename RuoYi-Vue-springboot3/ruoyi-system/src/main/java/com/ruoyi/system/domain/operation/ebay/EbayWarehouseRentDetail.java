package com.ruoyi.system.domain.operation.ebay;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/** eBay补货2.0仓租明细Sheet的一行源数据及其计算字段。 */
public class EbayWarehouseRentDetail
{
    private Long id;
    private String orderNo;
    private String warehouseCode;
    private String productCode;
    private String goodsBarcode;
    private String productName;
    private String referenceNo;
    private String billingTimeText;
    private String listingTimeText;
    private String dimensionsText;
    private String quantityText;
    private String volumeM3Text;
    private String productWeightKgText;
    private String warehouseRentExclTaxText;
    private String billingCurrency;
    private String inventoryAgeDaysText;
    private String goodsType;
    private String billingType;
    private String storagePhysicalForm;
    private String peakSeasonSurchargeExclTaxText;
    private String overAgeSurchargeExclTaxText;
    private String oversizedSurchargeExclTaxText;
    private String totalAmountExclTaxText;
    private String site;
    private String sku;
    private BigDecimal exchangeRate;
    private String exchangeRateMonth;
    private BigDecimal warehouseRentAmountCny;
    private String importBatchId;
    private String sourceFileName;
    private String sourceSheetName;
    private Integer sourceRowNum;
    private String importedBy;
    private LocalDateTime importTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getOrderNo() { return orderNo; }
    public void setOrderNo(String orderNo) { this.orderNo = orderNo; }
    public String getWarehouseCode() { return warehouseCode; }
    public void setWarehouseCode(String warehouseCode) { this.warehouseCode = warehouseCode; }
    public String getProductCode() { return productCode; }
    public void setProductCode(String productCode) { this.productCode = productCode; }
    public String getGoodsBarcode() { return goodsBarcode; }
    public void setGoodsBarcode(String goodsBarcode) { this.goodsBarcode = goodsBarcode; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public String getReferenceNo() { return referenceNo; }
    public void setReferenceNo(String referenceNo) { this.referenceNo = referenceNo; }
    public String getBillingTimeText() { return billingTimeText; }
    public void setBillingTimeText(String billingTimeText) { this.billingTimeText = billingTimeText; }
    public String getListingTimeText() { return listingTimeText; }
    public void setListingTimeText(String listingTimeText) { this.listingTimeText = listingTimeText; }
    public String getDimensionsText() { return dimensionsText; }
    public void setDimensionsText(String dimensionsText) { this.dimensionsText = dimensionsText; }
    public String getQuantityText() { return quantityText; }
    public void setQuantityText(String quantityText) { this.quantityText = quantityText; }
    public String getVolumeM3Text() { return volumeM3Text; }
    public void setVolumeM3Text(String volumeM3Text) { this.volumeM3Text = volumeM3Text; }
    public String getProductWeightKgText() { return productWeightKgText; }
    public void setProductWeightKgText(String value) { this.productWeightKgText = value; }
    public String getWarehouseRentExclTaxText() { return warehouseRentExclTaxText; }
    public void setWarehouseRentExclTaxText(String value) { this.warehouseRentExclTaxText = value; }
    public String getBillingCurrency() { return billingCurrency; }
    public void setBillingCurrency(String billingCurrency) { this.billingCurrency = billingCurrency; }
    public String getInventoryAgeDaysText() { return inventoryAgeDaysText; }
    public void setInventoryAgeDaysText(String value) { this.inventoryAgeDaysText = value; }
    public String getGoodsType() { return goodsType; }
    public void setGoodsType(String goodsType) { this.goodsType = goodsType; }
    public String getBillingType() { return billingType; }
    public void setBillingType(String billingType) { this.billingType = billingType; }
    public String getStoragePhysicalForm() { return storagePhysicalForm; }
    public void setStoragePhysicalForm(String value) { this.storagePhysicalForm = value; }
    public String getPeakSeasonSurchargeExclTaxText() { return peakSeasonSurchargeExclTaxText; }
    public void setPeakSeasonSurchargeExclTaxText(String value) { this.peakSeasonSurchargeExclTaxText = value; }
    public String getOverAgeSurchargeExclTaxText() { return overAgeSurchargeExclTaxText; }
    public void setOverAgeSurchargeExclTaxText(String value) { this.overAgeSurchargeExclTaxText = value; }
    public String getOversizedSurchargeExclTaxText() { return oversizedSurchargeExclTaxText; }
    public void setOversizedSurchargeExclTaxText(String value) { this.oversizedSurchargeExclTaxText = value; }
    public String getTotalAmountExclTaxText() { return totalAmountExclTaxText; }
    public void setTotalAmountExclTaxText(String value) { this.totalAmountExclTaxText = value; }
    public String getSite() { return site; }
    public void setSite(String site) { this.site = site; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public BigDecimal getExchangeRate() { return exchangeRate; }
    public void setExchangeRate(BigDecimal exchangeRate) { this.exchangeRate = exchangeRate; }
    public String getExchangeRateMonth() { return exchangeRateMonth; }
    public void setExchangeRateMonth(String value) { this.exchangeRateMonth = value; }
    public BigDecimal getWarehouseRentAmountCny() { return warehouseRentAmountCny; }
    public void setWarehouseRentAmountCny(BigDecimal value) { this.warehouseRentAmountCny = value; }
    public String getImportBatchId() { return importBatchId; }
    public void setImportBatchId(String importBatchId) { this.importBatchId = importBatchId; }
    public String getSourceFileName() { return sourceFileName; }
    public void setSourceFileName(String sourceFileName) { this.sourceFileName = sourceFileName; }
    public String getSourceSheetName() { return sourceSheetName; }
    public void setSourceSheetName(String value) { this.sourceSheetName = value; }
    public Integer getSourceRowNum() { return sourceRowNum; }
    public void setSourceRowNum(Integer sourceRowNum) { this.sourceRowNum = sourceRowNum; }
    public String getImportedBy() { return importedBy; }
    public void setImportedBy(String importedBy) { this.importedBy = importedBy; }
    public LocalDateTime getImportTime() { return importTime; }
    public void setImportTime(LocalDateTime importTime) { this.importTime = importTime; }
}
