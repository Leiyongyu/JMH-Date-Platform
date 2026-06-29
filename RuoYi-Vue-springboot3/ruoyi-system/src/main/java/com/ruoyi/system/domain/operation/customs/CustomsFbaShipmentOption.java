package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.math.BigDecimal;

public class CustomsFbaShipmentOption implements Serializable
{
    private static final long serialVersionUID = 1L;

    private String shipmentId;
    private Integer productCount;
    private Integer totalBoxCount;
    private BigDecimal totalQuantity;
    private BigDecimal totalGrossWeight;

    public String getShipmentId() { return shipmentId; }
    public void setShipmentId(String shipmentId) { this.shipmentId = shipmentId; }
    public Integer getProductCount() { return productCount; }
    public void setProductCount(Integer productCount) { this.productCount = productCount; }
    public Integer getTotalBoxCount() { return totalBoxCount; }
    public void setTotalBoxCount(Integer totalBoxCount) { this.totalBoxCount = totalBoxCount; }
    public BigDecimal getTotalQuantity() { return totalQuantity; }
    public void setTotalQuantity(BigDecimal totalQuantity) { this.totalQuantity = totalQuantity; }
    public BigDecimal getTotalGrossWeight() { return totalGrossWeight; }
    public void setTotalGrossWeight(BigDecimal totalGrossWeight) { this.totalGrossWeight = totalGrossWeight; }
}
