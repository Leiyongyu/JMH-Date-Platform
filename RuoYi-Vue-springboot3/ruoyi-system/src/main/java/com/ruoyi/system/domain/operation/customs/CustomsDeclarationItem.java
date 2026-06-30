package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.math.BigDecimal;

public class CustomsDeclarationItem extends CustomsProduct implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Integer quantity;
    private Integer boxCount;
    private String sourceOrderNo;
    private BigDecimal orderTotalCbm;
    private BigDecimal totalPrice;
    private BigDecimal totalWeight;

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
    public Integer getBoxCount() { return boxCount; }
    public void setBoxCount(Integer boxCount) { this.boxCount = boxCount; }
    public String getSourceOrderNo() { return sourceOrderNo; }
    public void setSourceOrderNo(String sourceOrderNo) { this.sourceOrderNo = sourceOrderNo; }
    public BigDecimal getOrderTotalCbm() { return orderTotalCbm; }
    public void setOrderTotalCbm(BigDecimal orderTotalCbm) { this.orderTotalCbm = orderTotalCbm; }
    public BigDecimal getTotalPrice() { return totalPrice; }
    public void setTotalPrice(BigDecimal totalPrice) { this.totalPrice = totalPrice; }
    public BigDecimal getTotalWeight() { return totalWeight; }
    public void setTotalWeight(BigDecimal totalWeight) { this.totalWeight = totalWeight; }
}
