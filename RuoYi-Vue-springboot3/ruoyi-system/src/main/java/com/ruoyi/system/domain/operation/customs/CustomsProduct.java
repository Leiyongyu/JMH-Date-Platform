package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

public class CustomsProduct implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String sku;
    private String descriptionCn;
    private String model;
    private String unit;
    private BigDecimal unitPriceUsd;
    private String currency;
    private BigDecimal singleWeight;
    private String hsCode;
    private String hsDescription;
    private String originCountry;
    private String destinationCountry;
    private String sourceLocation;
    private String exemption;
    private Date createdAt;
    private Date updatedAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getDescriptionCn() { return descriptionCn; }
    public void setDescriptionCn(String descriptionCn) { this.descriptionCn = descriptionCn; }
    public String getModel() { return model; }
    public void setModel(String model) { this.model = model; }
    public String getUnit() { return unit; }
    public void setUnit(String unit) { this.unit = unit; }
    public BigDecimal getUnitPriceUsd() { return unitPriceUsd; }
    public void setUnitPriceUsd(BigDecimal unitPriceUsd) { this.unitPriceUsd = unitPriceUsd; }
    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }
    public BigDecimal getSingleWeight() { return singleWeight; }
    public void setSingleWeight(BigDecimal singleWeight) { this.singleWeight = singleWeight; }
    public String getHsCode() { return hsCode; }
    public void setHsCode(String hsCode) { this.hsCode = hsCode; }
    public String getHsDescription() { return hsDescription; }
    public void setHsDescription(String hsDescription) { this.hsDescription = hsDescription; }
    public String getOriginCountry() { return originCountry; }
    public void setOriginCountry(String originCountry) { this.originCountry = originCountry; }
    public String getDestinationCountry() { return destinationCountry; }
    public void setDestinationCountry(String destinationCountry) { this.destinationCountry = destinationCountry; }
    public String getSourceLocation() { return sourceLocation; }
    public void setSourceLocation(String sourceLocation) { this.sourceLocation = sourceLocation; }
    public String getExemption() { return exemption; }
    public void setExemption(String exemption) { this.exemption = exemption; }
    public Date getCreatedAt() { return createdAt; }
    public void setCreatedAt(Date createdAt) { this.createdAt = createdAt; }
    public Date getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Date updatedAt) { this.updatedAt = updatedAt; }
}
