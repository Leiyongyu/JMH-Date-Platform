package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;

public class AmzOrderProfit implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private Integer sid;
    private String sellerSku;
    private BigDecimal grossMargin;
    private BigDecimal spendRate;
    private BigDecimal refundAmountRate;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Integer getSid() { return sid; }
    public void setSid(Integer sid) { this.sid = sid; }
    public String getSellerSku() { return sellerSku; }
    public void setSellerSku(String sellerSku) { this.sellerSku = sellerSku; }
    public BigDecimal getGrossMargin() { return grossMargin; }
    public void setGrossMargin(BigDecimal grossMargin) { this.grossMargin = grossMargin; }
    public BigDecimal getSpendRate() { return spendRate; }
    public void setSpendRate(BigDecimal spendRate) { this.spendRate = spendRate; }
    public BigDecimal getRefundAmountRate() { return refundAmountRate; }
    public void setRefundAmountRate(BigDecimal refundAmountRate) { this.refundAmountRate = refundAmountRate; }
}
