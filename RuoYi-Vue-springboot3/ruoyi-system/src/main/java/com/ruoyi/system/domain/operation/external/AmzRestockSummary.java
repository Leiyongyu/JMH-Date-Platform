package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;

public class AmzRestockSummary implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private String hashId;
    private Integer sid;
    private String msku;
    private Integer fbaSellable;
    private Integer fbaInbound;
    private Integer sales7d, sales14d, sales30d, sales60d;
    private BigDecimal avgSales14d, avgSales30d, avgSales60d;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getHashId() { return hashId; }
    public void setHashId(String hashId) { this.hashId = hashId; }
    public Integer getSid() { return sid; }
    public void setSid(Integer sid) { this.sid = sid; }
    public String getMsku() { return msku; }
    public void setMsku(String msku) { this.msku = msku; }
    public Integer getFbaSellable() { return fbaSellable; }
    public void setFbaSellable(Integer fbaSellable) { this.fbaSellable = fbaSellable; }
    public Integer getFbaInbound() { return fbaInbound; }
    public void setFbaInbound(Integer fbaInbound) { this.fbaInbound = fbaInbound; }
    public Integer getSales7d() { return sales7d; }
    public void setSales7d(Integer sales7d) { this.sales7d = sales7d; }
    public Integer getSales14d() { return sales14d; }
    public void setSales14d(Integer sales14d) { this.sales14d = sales14d; }
    public Integer getSales30d() { return sales30d; }
    public void setSales30d(Integer sales30d) { this.sales30d = sales30d; }
    public Integer getSales60d() { return sales60d; }
    public void setSales60d(Integer sales60d) { this.sales60d = sales60d; }
    public BigDecimal getAvgSales14d() { return avgSales14d; }
    public void setAvgSales14d(BigDecimal avgSales14d) { this.avgSales14d = avgSales14d; }
    public BigDecimal getAvgSales30d() { return avgSales30d; }
    public void setAvgSales30d(BigDecimal avgSales30d) { this.avgSales30d = avgSales30d; }
    public BigDecimal getAvgSales60d() { return avgSales60d; }
    public void setAvgSales60d(BigDecimal avgSales60d) { this.avgSales60d = avgSales60d; }
}
