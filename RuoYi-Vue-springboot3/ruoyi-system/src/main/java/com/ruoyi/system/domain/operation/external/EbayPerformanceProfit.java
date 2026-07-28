package com.ruoyi.system.domain.operation.external;

import java.math.BigDecimal;

/** eBay 月度绩效利润明细。 */
public class EbayPerformanceProfit
{
    private String statMonth;
    private String sku;
    private String brandCode;
    private String imageUrl;
    private String multiVariant;
    private BigDecimal grossProfit;
    private BigDecimal productSalesAmount;
    private BigDecimal receivableShippingAmount;
    private BigDecimal salesAmount;
    private BigDecimal refundAmount;
    private BigDecimal netSalesAmount;
    private String sourceFileName;
    private String sourceSheet;
    private Integer sourceRow;
    private String importedBy;

    public String getStatMonth()
    {
        return statMonth;
    }

    public void setStatMonth(String statMonth)
    {
        this.statMonth = statMonth;
    }

    public String getSku()
    {
        return sku;
    }

    public void setSku(String sku)
    {
        this.sku = sku;
    }

    public String getBrandCode()
    {
        return brandCode;
    }

    public void setBrandCode(String brandCode)
    {
        this.brandCode = brandCode;
    }

    public String getImageUrl()
    {
        return imageUrl;
    }

    public void setImageUrl(String imageUrl)
    {
        this.imageUrl = imageUrl;
    }

    public String getMultiVariant()
    {
        return multiVariant;
    }

    public void setMultiVariant(String multiVariant)
    {
        this.multiVariant = multiVariant;
    }

    public BigDecimal getGrossProfit()
    {
        return grossProfit;
    }

    public void setGrossProfit(BigDecimal grossProfit)
    {
        this.grossProfit = grossProfit;
    }

    public BigDecimal getProductSalesAmount()
    {
        return productSalesAmount;
    }

    public void setProductSalesAmount(BigDecimal productSalesAmount)
    {
        this.productSalesAmount = productSalesAmount;
    }

    public BigDecimal getReceivableShippingAmount()
    {
        return receivableShippingAmount;
    }

    public void setReceivableShippingAmount(BigDecimal receivableShippingAmount)
    {
        this.receivableShippingAmount = receivableShippingAmount;
    }

    public BigDecimal getSalesAmount()
    {
        return salesAmount;
    }

    public void setSalesAmount(BigDecimal salesAmount)
    {
        this.salesAmount = salesAmount;
    }

    public BigDecimal getRefundAmount()
    {
        return refundAmount;
    }

    public void setRefundAmount(BigDecimal refundAmount)
    {
        this.refundAmount = refundAmount;
    }

    public BigDecimal getNetSalesAmount()
    {
        return netSalesAmount;
    }

    public void setNetSalesAmount(BigDecimal netSalesAmount)
    {
        this.netSalesAmount = netSalesAmount;
    }

    public String getSourceFileName()
    {
        return sourceFileName;
    }

    public void setSourceFileName(String sourceFileName)
    {
        this.sourceFileName = sourceFileName;
    }

    public String getSourceSheet()
    {
        return sourceSheet;
    }

    public void setSourceSheet(String sourceSheet)
    {
        this.sourceSheet = sourceSheet;
    }

    public Integer getSourceRow()
    {
        return sourceRow;
    }

    public void setSourceRow(Integer sourceRow)
    {
        this.sourceRow = sourceRow;
    }

    public String getImportedBy()
    {
        return importedBy;
    }

    public void setImportedBy(String importedBy)
    {
        this.importedBy = importedBy;
    }
}
