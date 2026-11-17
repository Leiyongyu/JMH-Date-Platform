package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.List;

public class CustomsStockOrderOption implements Serializable
{
    private static final long serialVersionUID = 1L;

    private String overseasOrderNo;
    private String inboundOrderNo;
    private Integer productCount;
    private Integer totalBoxCount;
    private BigDecimal totalQuantity;
    private BigDecimal totalGrossWeight;
    private List<CustomsStockOrderSkuOption> items;

    public String getOverseasOrderNo() { return overseasOrderNo; }
    public void setOverseasOrderNo(String overseasOrderNo) { this.overseasOrderNo = overseasOrderNo; }
    public String getInboundOrderNo() { return inboundOrderNo; }
    public void setInboundOrderNo(String inboundOrderNo) { this.inboundOrderNo = inboundOrderNo; }
    public Integer getProductCount() { return productCount; }
    public void setProductCount(Integer productCount) { this.productCount = productCount; }
    public Integer getTotalBoxCount() { return totalBoxCount; }
    public void setTotalBoxCount(Integer totalBoxCount) { this.totalBoxCount = totalBoxCount; }
    public BigDecimal getTotalQuantity() { return totalQuantity; }
    public void setTotalQuantity(BigDecimal totalQuantity) { this.totalQuantity = totalQuantity; }
    public BigDecimal getTotalGrossWeight() { return totalGrossWeight; }
    public void setTotalGrossWeight(BigDecimal totalGrossWeight) { this.totalGrossWeight = totalGrossWeight; }
    public List<CustomsStockOrderSkuOption> getItems() { return items; }
    public void setItems(List<CustomsStockOrderSkuOption> items) { this.items = items; }
}
