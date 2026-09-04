package com.ruoyi.system.domain.operation.ebay;

import java.util.Objects;

/** 仓租增量覆盖键：仓库编码、商品编码与账单日。 */
public class EbayWarehouseProductKey
{
    private String warehouseCode;
    private String productCode;
    private String billingTimeText;

    public EbayWarehouseProductKey() { }

    public EbayWarehouseProductKey(
            String warehouseCode,
            String productCode,
            String billingTimeText)
    {
        this.warehouseCode = warehouseCode;
        this.productCode = productCode;
        this.billingTimeText = billingTimeText;
    }

    public String getWarehouseCode() { return warehouseCode; }
    public void setWarehouseCode(String value) { this.warehouseCode = value; }
    public String getProductCode() { return productCode; }
    public void setProductCode(String value) { this.productCode = value; }
    public String getBillingTimeText() { return billingTimeText; }
    public void setBillingTimeText(String value) { this.billingTimeText = value; }

    @Override
    public boolean equals(Object value)
    {
        if (this == value) return true;
        if (!(value instanceof EbayWarehouseProductKey other)) return false;
        return Objects.equals(warehouseCode, other.warehouseCode)
                && Objects.equals(productCode, other.productCode)
                && Objects.equals(billingTimeText, other.billingTimeText);
    }

    @Override
    public int hashCode()
    {
        return Objects.hash(warehouseCode, productCode, billingTimeText);
    }
}
