package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.math.BigDecimal;
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
    private String remark;
    private String customsUnit;
    private String declarationElements;
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
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
    public String getCustomsUnit() { return customsUnit; }
    public void setCustomsUnit(String customsUnit) { this.customsUnit = customsUnit; }
    public String getDeclarationElements() { return declarationElements; }
    public void setDeclarationElements(String declarationElements) { this.declarationElements = declarationElements; }
    public Date getCreatedAt() { return createdAt; }
    public void setCreatedAt(Date createdAt) { this.createdAt = createdAt; }
    public Date getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Date updatedAt) { this.updatedAt = updatedAt; }
}
