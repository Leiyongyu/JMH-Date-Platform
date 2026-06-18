package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;

/**
 * eBay链接模板表
 */
public class EbayLinkTemplate implements Serializable
{
    private static final long serialVersionUID = 1L;

    private String site;
    private String presaleUrl;
    private String soldUrl;
    private Integer profitRate;
    private BigDecimal exchangeRate;

    public String getSite() { return site; }
    public void setSite(String site) { this.site = site; }
    public String getPresaleUrl() { return presaleUrl; }
    public void setPresaleUrl(String presaleUrl) { this.presaleUrl = presaleUrl; }
    public String getSoldUrl() { return soldUrl; }
    public void setSoldUrl(String soldUrl) { this.soldUrl = soldUrl; }
    public Integer getProfitRate() { return profitRate; }
    public void setProfitRate(Integer profitRate) { this.profitRate = profitRate; }
    public BigDecimal getExchangeRate() { return exchangeRate; }
    public void setExchangeRate(BigDecimal exchangeRate) { this.exchangeRate = exchangeRate; }
}
