package com.ruoyi.system.domain.operation.ebay;

/**
 * eBay SKU 与 OE 对照关系。
 */
public class EbaySkuOeMapping
{
    private Long id;
    private String sku;
    private String oe;
    private Integer oeIndex;
    private String sourceFileName;

    public Long getId()
    {
        return id;
    }

    public void setId(Long id)
    {
        this.id = id;
    }

    public String getSku()
    {
        return sku;
    }

    public void setSku(String sku)
    {
        this.sku = sku;
    }

    public String getOe()
    {
        return oe;
    }

    public void setOe(String oe)
    {
        this.oe = oe;
    }

    public Integer getOeIndex()
    {
        return oeIndex;
    }

    public void setOeIndex(Integer oeIndex)
    {
        this.oeIndex = oeIndex;
    }

    public String getSourceFileName()
    {
        return sourceFileName;
    }

    public void setSourceFileName(String sourceFileName)
    {
        this.sourceFileName = sourceFileName;
    }
}
