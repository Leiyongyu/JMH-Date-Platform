package com.ruoyi.system.domain.report;

import java.io.Serializable;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * 月初期初库存货值检查结果 — 对应 jmh_report.ads_monthly_opening_inventory_value
 */
public class InventoryOpeningValue implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String batchId;
    private LocalDate reportDate;
    private String sourceSystem;
    private String platform;
    private String warehouseType;
    private String warehouseTypeName;
    private Long sysWid;
    private String warehouseName;
    private String sellerName;
    private String sku;
    private String fnsku;
    private String spu;
    private String productName;
    private String brand;
    private String category1;
    private String category2;
    private String category3;
    private BigDecimal openingQty;
    private BigDecimal openingCost;
    private BigDecimal unitCost;
    private String costStatus;      // OK / ZERO_COST / ZERO_QTY / MISSING_COST
    private Integer anomalyFlag;    // 1=异常 0=正常
    private String anomalyReason;
    private Long sourceOdsId;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getBatchId() { return batchId; }
    public void setBatchId(String batchId) { this.batchId = batchId; }
    public LocalDate getReportDate() { return reportDate; }
    public void setReportDate(LocalDate reportDate) { this.reportDate = reportDate; }
    public String getSourceSystem() { return sourceSystem; }
    public void setSourceSystem(String sourceSystem) { this.sourceSystem = sourceSystem; }
    public String getPlatform() { return platform; }
    public void setPlatform(String platform) { this.platform = platform; }
    public String getWarehouseType() { return warehouseType; }
    public void setWarehouseType(String warehouseType) { this.warehouseType = warehouseType; }
    public String getWarehouseTypeName() { return warehouseTypeName; }
    public void setWarehouseTypeName(String warehouseTypeName) { this.warehouseTypeName = warehouseTypeName; }
    public Long getSysWid() { return sysWid; }
    public void setSysWid(Long sysWid) { this.sysWid = sysWid; }
    public String getWarehouseName() { return warehouseName; }
    public void setWarehouseName(String warehouseName) { this.warehouseName = warehouseName; }
    public String getSellerName() { return sellerName; }
    public void setSellerName(String sellerName) { this.sellerName = sellerName; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getFnsku() { return fnsku; }
    public void setFnsku(String fnsku) { this.fnsku = fnsku; }
    public String getSpu() { return spu; }
    public void setSpu(String spu) { this.spu = spu; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public String getBrand() { return brand; }
    public void setBrand(String brand) { this.brand = brand; }
    public String getCategory1() { return category1; }
    public void setCategory1(String category1) { this.category1 = category1; }
    public String getCategory2() { return category2; }
    public void setCategory2(String category2) { this.category2 = category2; }
    public String getCategory3() { return category3; }
    public void setCategory3(String category3) { this.category3 = category3; }
    public BigDecimal getOpeningQty() { return openingQty; }
    public void setOpeningQty(BigDecimal openingQty) { this.openingQty = openingQty; }
    public BigDecimal getOpeningCost() { return openingCost; }
    public void setOpeningCost(BigDecimal openingCost) { this.openingCost = openingCost; }
    public BigDecimal getUnitCost() { return unitCost; }
    public void setUnitCost(BigDecimal unitCost) { this.unitCost = unitCost; }
    public String getCostStatus() { return costStatus; }
    public void setCostStatus(String costStatus) { this.costStatus = costStatus; }
    public Integer getAnomalyFlag() { return anomalyFlag; }
    public void setAnomalyFlag(Integer anomalyFlag) { this.anomalyFlag = anomalyFlag; }
    public String getAnomalyReason() { return anomalyReason; }
    public void setAnomalyReason(String anomalyReason) { this.anomalyReason = anomalyReason; }
    public Long getSourceOdsId() { return sourceOdsId; }
    public void setSourceOdsId(Long sourceOdsId) { this.sourceOdsId = sourceOdsId; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
