package com.ruoyi.system.domain.operation.ebay;

import java.util.List;

/** eBay竞品商品库导出请求。 */
public class EbayCompetitorExportRequest
{
    /** true导出全部商品；false仅导出ids指定的商品。 */
    private boolean exportAll;

    /** 需要导出的商品主键。 */
    private List<Long> ids;

    public boolean isExportAll()
    {
        return exportAll;
    }

    public void setExportAll(boolean exportAll)
    {
        this.exportAll = exportAll;
    }

    public List<Long> getIds()
    {
        return ids;
    }

    public void setIds(List<Long> ids)
    {
        this.ids = ids;
    }
}
