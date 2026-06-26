package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.math.BigDecimal;

public class CustomsDeclarationItem extends CustomsProduct implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Integer quantity;
    private BigDecimal totalPrice;
    private BigDecimal totalWeight;

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
    public BigDecimal getTotalPrice() { return totalPrice; }
    public void setTotalPrice(BigDecimal totalPrice) { this.totalPrice = totalPrice; }
    public BigDecimal getTotalWeight() { return totalWeight; }
    public void setTotalWeight(BigDecimal totalWeight) { this.totalWeight = totalWeight; }
}
