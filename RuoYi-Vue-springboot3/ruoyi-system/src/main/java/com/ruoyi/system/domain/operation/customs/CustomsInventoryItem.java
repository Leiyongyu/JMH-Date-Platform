package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Date;

public class CustomsInventoryItem implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String productCode;
    private String productName;
    private String sku;
    private String purchaseQuantity;
    private String unit;
    private String taxIncludedPrice;
    private String purchaseDate;
    private String inboundDate;
    private BigDecimal inboundQuantity;
    private String inboundRemark;
    private String outboundDate;
    private BigDecimal czechWarehouseQty;
    private BigDecimal ukWarehouseQty;
    private BigDecimal usWarehouseQty;
    private BigDecimal deWarehouseQty;
    private BigDecimal fbaDeQty;
    private BigDecimal fbaUkQty;
    private BigDecimal fbaUsQty;
    private BigDecimal fbaFrQty;
    private BigDecimal remainingStock;
    private BigDecimal autoCzechWarehouseQty;
    private BigDecimal autoUkWarehouseQty;
    private BigDecimal autoUsWarehouseQty;
    private BigDecimal autoDeWarehouseQty;
    private BigDecimal autoFbaDeQty;
    private BigDecimal autoFbaUkQty;
    private BigDecimal autoFbaUsQty;
    private BigDecimal autoFbaFrQty;
    private BigDecimal autoRemainingStock;
    private BigDecimal declaredCzechWarehouseQty;
    private BigDecimal declaredUkWarehouseQty;
    private BigDecimal declaredUsWarehouseQty;
    private BigDecimal declaredDeWarehouseQty;
    private BigDecimal declaredFbaDeQty;
    private BigDecimal declaredFbaUkQty;
    private BigDecimal declaredFbaUsQty;
    private BigDecimal declaredFbaFrQty;
    private BigDecimal declaredUnknownWarehouseQty;
    private BigDecimal declaredTotalQty;
    private BigDecimal availableRemainingStock;
    private Map<String, List<CustomsDeclarationGenerateLog>> declarationLogs;
    private String remark;
    private String customsUnit;
    private String declarationElements;
    private String hsCode;
    private String hsDescription;
    private Date createdAt;
    private Date updatedAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getProductCode() { return productCode; }
    public void setProductCode(String productCode) { this.productCode = productCode; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getPurchaseQuantity() { return purchaseQuantity; }
    public void setPurchaseQuantity(String purchaseQuantity) { this.purchaseQuantity = purchaseQuantity; }
    public String getUnit() { return unit; }
    public void setUnit(String unit) { this.unit = unit; }
    public String getTaxIncludedPrice() { return taxIncludedPrice; }
    public void setTaxIncludedPrice(String taxIncludedPrice) { this.taxIncludedPrice = taxIncludedPrice; }
    public String getPurchaseDate() { return purchaseDate; }
    public void setPurchaseDate(String purchaseDate) { this.purchaseDate = purchaseDate; }
    public String getInboundDate() { return inboundDate; }
    public void setInboundDate(String inboundDate) { this.inboundDate = inboundDate; }
    public BigDecimal getInboundQuantity() { return inboundQuantity; }
    public void setInboundQuantity(BigDecimal inboundQuantity) { this.inboundQuantity = inboundQuantity; }
    public String getInboundRemark() { return inboundRemark; }
    public void setInboundRemark(String inboundRemark) { this.inboundRemark = inboundRemark; }
    public String getOutboundDate() { return outboundDate; }
    public void setOutboundDate(String outboundDate) { this.outboundDate = outboundDate; }
    public BigDecimal getCzechWarehouseQty() { return czechWarehouseQty; }
    public void setCzechWarehouseQty(BigDecimal czechWarehouseQty) { this.czechWarehouseQty = czechWarehouseQty; }
    public BigDecimal getUkWarehouseQty() { return ukWarehouseQty; }
    public void setUkWarehouseQty(BigDecimal ukWarehouseQty) { this.ukWarehouseQty = ukWarehouseQty; }
    public BigDecimal getUsWarehouseQty() { return usWarehouseQty; }
    public void setUsWarehouseQty(BigDecimal usWarehouseQty) { this.usWarehouseQty = usWarehouseQty; }
    public BigDecimal getDeWarehouseQty() { return deWarehouseQty; }
    public void setDeWarehouseQty(BigDecimal deWarehouseQty) { this.deWarehouseQty = deWarehouseQty; }
    public BigDecimal getFbaDeQty() { return fbaDeQty; }
    public void setFbaDeQty(BigDecimal fbaDeQty) { this.fbaDeQty = fbaDeQty; }
    public BigDecimal getFbaUkQty() { return fbaUkQty; }
    public void setFbaUkQty(BigDecimal fbaUkQty) { this.fbaUkQty = fbaUkQty; }
    public BigDecimal getFbaUsQty() { return fbaUsQty; }
    public void setFbaUsQty(BigDecimal fbaUsQty) { this.fbaUsQty = fbaUsQty; }
    public BigDecimal getFbaFrQty() { return fbaFrQty; }
    public void setFbaFrQty(BigDecimal fbaFrQty) { this.fbaFrQty = fbaFrQty; }
    public BigDecimal getRemainingStock() { return remainingStock; }
    public void setRemainingStock(BigDecimal remainingStock) { this.remainingStock = remainingStock; }
    public BigDecimal getAutoCzechWarehouseQty() { return autoCzechWarehouseQty; }
    public void setAutoCzechWarehouseQty(BigDecimal autoCzechWarehouseQty) { this.autoCzechWarehouseQty = autoCzechWarehouseQty; }
    public BigDecimal getAutoUkWarehouseQty() { return autoUkWarehouseQty; }
    public void setAutoUkWarehouseQty(BigDecimal autoUkWarehouseQty) { this.autoUkWarehouseQty = autoUkWarehouseQty; }
    public BigDecimal getAutoUsWarehouseQty() { return autoUsWarehouseQty; }
    public void setAutoUsWarehouseQty(BigDecimal autoUsWarehouseQty) { this.autoUsWarehouseQty = autoUsWarehouseQty; }
    public BigDecimal getAutoDeWarehouseQty() { return autoDeWarehouseQty; }
    public void setAutoDeWarehouseQty(BigDecimal autoDeWarehouseQty) { this.autoDeWarehouseQty = autoDeWarehouseQty; }
    public BigDecimal getAutoFbaDeQty() { return autoFbaDeQty; }
    public void setAutoFbaDeQty(BigDecimal autoFbaDeQty) { this.autoFbaDeQty = autoFbaDeQty; }
    public BigDecimal getAutoFbaUkQty() { return autoFbaUkQty; }
    public void setAutoFbaUkQty(BigDecimal autoFbaUkQty) { this.autoFbaUkQty = autoFbaUkQty; }
    public BigDecimal getAutoFbaUsQty() { return autoFbaUsQty; }
    public void setAutoFbaUsQty(BigDecimal autoFbaUsQty) { this.autoFbaUsQty = autoFbaUsQty; }
    public BigDecimal getAutoFbaFrQty() { return autoFbaFrQty; }
    public void setAutoFbaFrQty(BigDecimal autoFbaFrQty) { this.autoFbaFrQty = autoFbaFrQty; }
    public BigDecimal getAutoRemainingStock() { return autoRemainingStock; }
    public void setAutoRemainingStock(BigDecimal autoRemainingStock) { this.autoRemainingStock = autoRemainingStock; }
    public BigDecimal getDeclaredCzechWarehouseQty() { return declaredCzechWarehouseQty; }
    public void setDeclaredCzechWarehouseQty(BigDecimal declaredCzechWarehouseQty) { this.declaredCzechWarehouseQty = declaredCzechWarehouseQty; }
    public BigDecimal getDeclaredUkWarehouseQty() { return declaredUkWarehouseQty; }
    public void setDeclaredUkWarehouseQty(BigDecimal declaredUkWarehouseQty) { this.declaredUkWarehouseQty = declaredUkWarehouseQty; }
    public BigDecimal getDeclaredUsWarehouseQty() { return declaredUsWarehouseQty; }
    public void setDeclaredUsWarehouseQty(BigDecimal declaredUsWarehouseQty) { this.declaredUsWarehouseQty = declaredUsWarehouseQty; }
    public BigDecimal getDeclaredDeWarehouseQty() { return declaredDeWarehouseQty; }
    public void setDeclaredDeWarehouseQty(BigDecimal declaredDeWarehouseQty) { this.declaredDeWarehouseQty = declaredDeWarehouseQty; }
    public BigDecimal getDeclaredFbaDeQty() { return declaredFbaDeQty; }
    public void setDeclaredFbaDeQty(BigDecimal declaredFbaDeQty) { this.declaredFbaDeQty = declaredFbaDeQty; }
    public BigDecimal getDeclaredFbaUkQty() { return declaredFbaUkQty; }
    public void setDeclaredFbaUkQty(BigDecimal declaredFbaUkQty) { this.declaredFbaUkQty = declaredFbaUkQty; }
    public BigDecimal getDeclaredFbaUsQty() { return declaredFbaUsQty; }
    public void setDeclaredFbaUsQty(BigDecimal declaredFbaUsQty) { this.declaredFbaUsQty = declaredFbaUsQty; }
    public BigDecimal getDeclaredFbaFrQty() { return declaredFbaFrQty; }
    public void setDeclaredFbaFrQty(BigDecimal declaredFbaFrQty) { this.declaredFbaFrQty = declaredFbaFrQty; }
    public BigDecimal getDeclaredUnknownWarehouseQty() { return declaredUnknownWarehouseQty; }
    public void setDeclaredUnknownWarehouseQty(BigDecimal declaredUnknownWarehouseQty) { this.declaredUnknownWarehouseQty = declaredUnknownWarehouseQty; }
    public BigDecimal getDeclaredTotalQty() { return declaredTotalQty; }
    public void setDeclaredTotalQty(BigDecimal declaredTotalQty) { this.declaredTotalQty = declaredTotalQty; }
    public BigDecimal getAvailableRemainingStock() { return availableRemainingStock; }
    public void setAvailableRemainingStock(BigDecimal availableRemainingStock) { this.availableRemainingStock = availableRemainingStock; }
    public Map<String, List<CustomsDeclarationGenerateLog>> getDeclarationLogs() { return declarationLogs; }
    public void setDeclarationLogs(Map<String, List<CustomsDeclarationGenerateLog>> declarationLogs) { this.declarationLogs = declarationLogs; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
    public String getCustomsUnit() { return customsUnit; }
    public void setCustomsUnit(String customsUnit) { this.customsUnit = customsUnit; }
    public String getDeclarationElements() { return declarationElements; }
    public void setDeclarationElements(String declarationElements) { this.declarationElements = declarationElements; }
    public String getHsCode() { return hsCode; }
    public void setHsCode(String hsCode) { this.hsCode = hsCode; }
    public String getHsDescription() { return hsDescription; }
    public void setHsDescription(String hsDescription) { this.hsDescription = hsDescription; }
    public Date getCreatedAt() { return createdAt; }
    public void setCreatedAt(Date createdAt) { this.createdAt = createdAt; }
    public Date getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Date updatedAt) { this.updatedAt = updatedAt; }
}
