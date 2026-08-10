package com.ruoyi.system.domain.operation.ebay;

import java.util.List;

/**
 * eBay 商品价格查询请求。
 */
public class EbayPriceSearchRequest
{
    private List<String> keywords;
    private String site = "de";
    private String inputType = "auto";

    public List<String> getKeywords()
    {
        return keywords;
    }

    public void setKeywords(List<String> keywords)
    {
        this.keywords = keywords;
    }

    public String getSite()
    {
        return site;
    }

    public void setSite(String site)
    {
        this.site = site;
    }

    public String getInputType()
    {
        return inputType;
    }

    public void setInputType(String inputType)
    {
        this.inputType = inputType;
    }
}
