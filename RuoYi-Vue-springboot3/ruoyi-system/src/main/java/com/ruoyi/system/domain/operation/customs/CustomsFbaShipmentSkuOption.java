package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.math.BigDecimal;

public class CustomsFbaShipmentSkuOption implements Serializable
{
    private static final long serialVersionUID = 1L;

    private String shipmentId;
    private String sku;
    private BigDecimal totalQuantity;
    private Integer totalBoxCount;
    private Integer isTax;

    public String getShipmentId() { return shipmentId; }
    public void setShipmentId(String shipmentId) { this.shipmentId = shipmentId; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public BigDecimal getTotalQuantity() { return totalQuantity; }
    public void setTotalQuantity(BigDecimal totalQuantity) { this.totalQuantity = totalQuantity; }
    public Integer getTotalBoxCount() { return totalBoxCount; }
    public void setTotalBoxCount(Integer totalBoxCount) { this.totalBoxCount = totalBoxCount; }
    public Integer getIsTax() { return isTax; }
    public void setIsTax(Integer isTax) { this.isTax = isTax; }
}
