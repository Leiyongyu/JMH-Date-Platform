package com.ruoyi.system.domain.operation;

/**
 * Amazon补货销量明细请求。
 */
public class AmzSalesBreakdownRequest extends EbayReplenishmentSearchRequest
{
    /** 当前行仓库SKU，弹窗明细按这个SKU精确匹配 */
    private String warehouseSku;

    /** 销量字段：sales7d/sales14d/sales30d/sales60d/salesSpeed14d/salesSpeed30d/salesSpeed60d/avgMonthlySales */
    private String field;

    public String getWarehouseSku()
    {
        return warehouseSku;
    }

    public void setWarehouseSku(String warehouseSku)
    {
        this.warehouseSku = warehouseSku;
    }

    public String getField()
    {
        return field;
    }

    public void setField(String field)
    {
        this.field = field;
    }
}
