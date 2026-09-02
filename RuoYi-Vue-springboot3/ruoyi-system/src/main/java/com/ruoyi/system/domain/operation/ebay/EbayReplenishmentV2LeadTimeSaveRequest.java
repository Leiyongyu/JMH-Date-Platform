package com.ruoyi.system.domain.operation.ebay;

/** eBay补货2.0单个人工时效字段自动保存请求。 */
public class EbayReplenishmentV2LeadTimeSaveRequest
{
    private String site;
    private String sku;
    private String field;
    private Integer days;

    public String getSite() { return site; }
    public void setSite(String site) { this.site = site; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getField() { return field; }
    public void setField(String field) { this.field = field; }
    public Integer getDays() { return days; }
    public void setDays(Integer days) { this.days = days; }
}
