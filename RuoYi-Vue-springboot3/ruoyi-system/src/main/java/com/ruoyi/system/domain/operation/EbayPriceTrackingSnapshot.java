package com.ruoyi.system.domain.operation;

import java.math.BigDecimal;
import java.util.Date;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.ruoyi.common.annotation.Excel;
import com.ruoyi.common.core.domain.BaseEntity;

public class EbayPriceTrackingSnapshot extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    private Long id;

    @Excel(name = "站点")
    private String site;

    @Excel(name = "SKU")
    private String sku;

    @Excel(name = "产品名称")
    private String productName;

    @Excel(name = "等级")
    private String skuLevel;

    @Excel(name = "我方最低价")
    private BigDecimal ourLowestPrice;

    @Excel(name = "跟卖价")
    private BigDecimal trackingPrice;

    @Excel(name = "跟卖利润率")
    private BigDecimal trackingProfitMargin;

    @Excel(name = "底线价")
    private BigDecimal floorPrice;

    @Excel(name = "退货率")
    private BigDecimal returnRate;

    @Excel(name = "近3天销量")
    private Integer sales3d;

    @Excel(name = "近7天销量")
    private Integer sales7d;

    @Excel(name = "近30天销量")
    private Integer sales30d;

    @Excel(name = "近90天销量")
    private Integer sales90d;

    @Excel(name = "历史最大月销")
    private Integer maxMonthlySales;

    @Excel(name = "海外仓库存")
    private Integer overseasStock;

    @Excel(name = "海外仓库龄")
    private Integer overseasStockAgeDays;

    @Excel(name = "库销比")
    private BigDecimal stockSalesRatio;

    @Excel(name = "预估补货量")
    private Integer estimatedReplenishQty;

    @Excel(name = "品牌")
    private String brandCode;

    @Excel(name = "操作员")
    private String operatorName;

    @Excel(name = "OE号")
    private String oeNumber;

    @Excel(name = "售前链接")
    private String presaleUrl;

    @Excel(name = "售后链接")
    private String soldUrl;

    private String remark;

    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private Date calcTime;

    // 查询参数
    private String sortField;
    private String sortOrder;
    private List<EbayReplenishmentSearchRequest.FilterItem> filters;

    // ====== getters/setters ======
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSite() { return site; }
    public void setSite(String site) { this.site = site; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public String getSkuLevel() { return skuLevel; }
    public void setSkuLevel(String skuLevel) { this.skuLevel = skuLevel; }
    public BigDecimal getOurLowestPrice() { return ourLowestPrice; }
    public void setOurLowestPrice(BigDecimal ourLowestPrice) { this.ourLowestPrice = ourLowestPrice; }
    public BigDecimal getTrackingPrice() { return trackingPrice; }
    public void setTrackingPrice(BigDecimal trackingPrice) { this.trackingPrice = trackingPrice; }
    public BigDecimal getTrackingProfitMargin() { return trackingProfitMargin; }
    public void setTrackingProfitMargin(BigDecimal trackingProfitMargin) { this.trackingProfitMargin = trackingProfitMargin; }
    public BigDecimal getFloorPrice() { return floorPrice; }
    public void setFloorPrice(BigDecimal floorPrice) { this.floorPrice = floorPrice; }
    public BigDecimal getReturnRate() { return returnRate; }
    public void setReturnRate(BigDecimal returnRate) { this.returnRate = returnRate; }
    public Integer getSales3d() { return sales3d; }
    public void setSales3d(Integer sales3d) { this.sales3d = sales3d; }
    public Integer getSales7d() { return sales7d; }
    public void setSales7d(Integer sales7d) { this.sales7d = sales7d; }
    public Integer getSales30d() { return sales30d; }
    public void setSales30d(Integer sales30d) { this.sales30d = sales30d; }
    public Integer getSales90d() { return sales90d; }
    public void setSales90d(Integer sales90d) { this.sales90d = sales90d; }
    public Integer getMaxMonthlySales() { return maxMonthlySales; }
    public void setMaxMonthlySales(Integer maxMonthlySales) { this.maxMonthlySales = maxMonthlySales; }
    public Integer getOverseasStock() { return overseasStock; }
    public void setOverseasStock(Integer overseasStock) { this.overseasStock = overseasStock; }
    public Integer getOverseasStockAgeDays() { return overseasStockAgeDays; }
    public void setOverseasStockAgeDays(Integer overseasStockAgeDays) { this.overseasStockAgeDays = overseasStockAgeDays; }
    public BigDecimal getStockSalesRatio() { return stockSalesRatio; }
    public void setStockSalesRatio(BigDecimal stockSalesRatio) { this.stockSalesRatio = stockSalesRatio; }
    public Integer getEstimatedReplenishQty() { return estimatedReplenishQty; }
    public void setEstimatedReplenishQty(Integer estimatedReplenishQty) { this.estimatedReplenishQty = estimatedReplenishQty; }
    public String getBrandCode() { return brandCode; }
    public void setBrandCode(String brandCode) { this.brandCode = brandCode; }
    public String getOperatorName() { return operatorName; }
    public void setOperatorName(String operatorName) { this.operatorName = operatorName; }
    public String getOeNumber() { return oeNumber; }
    public void setOeNumber(String oeNumber) { this.oeNumber = oeNumber; }
    public String getPresaleUrl() { return presaleUrl; }
    public void setPresaleUrl(String presaleUrl) { this.presaleUrl = presaleUrl; }
    public String getSoldUrl() { return soldUrl; }
    public void setSoldUrl(String soldUrl) { this.soldUrl = soldUrl; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
    public Date getCalcTime() { return calcTime; }
    public void setCalcTime(Date calcTime) { this.calcTime = calcTime; }
    public String getSortField() { return sortField; }
    public void setSortField(String sortField) { this.sortField = sortField; }
    public String getSortOrder() { return sortOrder; }
    public void setSortOrder(String sortOrder) { this.sortOrder = sortOrder; }
    public List<EbayReplenishmentSearchRequest.FilterItem> getFilters() { return filters; }
    public void setFilters(List<EbayReplenishmentSearchRequest.FilterItem> filters) { this.filters = filters; }
}
