package com.ruoyi.system.domain.operation.ebay;

import java.util.List;

/**
 * eBay 价格查询结果导出请求。
 */
public class EbayPriceExportRequest
{
    private List<EbayItemDetail> items;

    public List<EbayItemDetail> getItems()
    {
        return items;
    }

    public void setItems(List<EbayItemDetail> items)
    {
        this.items = items;
    }
}
