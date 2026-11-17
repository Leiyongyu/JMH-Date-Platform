package com.ruoyi.system.domain.operation.ebay;

/** eBay补货2.0按站点和SKU维护的人工时效。 */
public class EbayReplenishmentV2LeadTime
{
    private Long id;
    private String site;
    private String sku;
    private Integer chengduWarehouseToWarehouseDays;
    private Integer chengduQcOutboundDays;
    private Integer overseasTransitToListingDays;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSite() { return site; }
    public void setSite(String site) { this.site = site; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public Integer getChengduWarehouseToWarehouseDays() { return chengduWarehouseToWarehouseDays; }
    public void setChengduWarehouseToWarehouseDays(Integer value) { this.chengduWarehouseToWarehouseDays = value; }
    public Integer getChengduQcOutboundDays() { return chengduQcOutboundDays; }
    public void setChengduQcOutboundDays(Integer value) { this.chengduQcOutboundDays = value; }
    public Integer getOverseasTransitToListingDays() { return overseasTransitToListingDays; }
    public void setOverseasTransitToListingDays(Integer value) { this.overseasTransitToListingDays = value; }
}
