package com.ruoyi.system.domain.operation;

import java.math.BigDecimal;
import java.util.Date;
import com.fasterxml.jackson.annotation.JsonFormat;
import com.ruoyi.common.annotation.Excel;
import com.ruoyi.common.core.domain.BaseEntity;

public class AmzReplenishmentSnapshot extends BaseEntity
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private Integer sid;

    @Excel(name = "Seller SKU")
    private String sellerSku;

    @Excel(name = "仓库SKU")
    private String warehouseSku;

    @Excel(name = "仓库")
    private String warehouseName;

    @Excel(name = "ASIN")
    private String asin;

    @Excel(name = "负责人")
    private String principalName;

    @Excel(name = "店铺")
    private String storeName;

    @Excel(name = "产品分类")
    private String productCategory;

    @Excel(name = "评分")
    private BigDecimal rating;

    @Excel(name = "评论数")
    private Integer reviewCount;

    @Excel(name = "广告费率")
    private BigDecimal adRate;

    @Excel(name = "30天利润率")
    private BigDecimal profitRate30d;

    @Excel(name = "90天退款率")
    private BigDecimal refundRate90d;

    @Excel(name = "已采购数量")
    private Integer purchasedQty;

    @Excel(name = "国内仓库存")
    private Integer domesticStock;

    @Excel(name = "待出库")
    private Integer pendingShipQty;

    @Excel(name = "FBA在库")
    private Integer fbaStock;

    @Excel(name = "FBA在途")
    private Integer fbaInbound;

    @Excel(name = "总库存")
    private Integer totalInventory;

    @Excel(name = "7天销量")
    private Integer sales7d;

    @Excel(name = "14天销量")
    private Integer sales14d;

    @Excel(name = "30天销量")
    private Integer sales30d;

    @Excel(name = "60天销量")
    private Integer sales60d;

    @Excel(name = "14日均销")
    private BigDecimal salesSpeed14d;

    @Excel(name = "30日均销")
    private BigDecimal salesSpeed30d;

    @Excel(name = "60日均销")
    private BigDecimal salesSpeed60d;

    @Excel(name = "平均月销量")
    private BigDecimal avgMonthlySales;

    @Excel(name = "安全库存")
    private BigDecimal safetyStock;

    @Excel(name = "发货量")
    private BigDecimal shipQty;

    @Excel(name = "补货量")
    private BigDecimal replenishQty;

    @Excel(name = "补货时间")
    private BigDecimal restockDays;

	private String regionGroup;

    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private Date calcTime;

    private String sortField;
    private String sortOrder;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Integer getSid() { return sid; }
    public void setSid(Integer sid) { this.sid = sid; }
    public String getSellerSku() { return sellerSku; }
    public void setSellerSku(String sellerSku) { this.sellerSku = sellerSku; }
    public String getWarehouseSku() { return warehouseSku; }
    public void setWarehouseSku(String warehouseSku) { this.warehouseSku = warehouseSku; }
    public String getWarehouseName() { return warehouseName; }
    public void setWarehouseName(String warehouseName) { this.warehouseName = warehouseName; }
    public String getAsin() { return asin; }
    public void setAsin(String asin) { this.asin = asin; }
    public String getPrincipalName() { return principalName; }
    public void setPrincipalName(String principalName) { this.principalName = principalName; }
    public String getStoreName() { return storeName; }
    public void setStoreName(String storeName) { this.storeName = storeName; }
    public String getProductCategory() { return productCategory; }
    public void setProductCategory(String productCategory) { this.productCategory = productCategory; }
    public BigDecimal getRating() { return rating; }
    public void setRating(BigDecimal rating) { this.rating = rating; }
    public Integer getReviewCount() { return reviewCount; }
    public void setReviewCount(Integer reviewCount) { this.reviewCount = reviewCount; }
    public BigDecimal getAdRate() { return adRate; }
    public void setAdRate(BigDecimal adRate) { this.adRate = adRate; }
    public BigDecimal getProfitRate30d() { return profitRate30d; }
    public void setProfitRate30d(BigDecimal profitRate30d) { this.profitRate30d = profitRate30d; }
    public BigDecimal getRefundRate90d() { return refundRate90d; }
    public void setRefundRate90d(BigDecimal refundRate90d) { this.refundRate90d = refundRate90d; }
    public Integer getPurchasedQty() { return purchasedQty; }
    public void setPurchasedQty(Integer purchasedQty) { this.purchasedQty = purchasedQty; }
    public Integer getDomesticStock() { return domesticStock; }
    public void setDomesticStock(Integer domesticStock) { this.domesticStock = domesticStock; }
    public Integer getPendingShipQty() { return pendingShipQty; }
    public void setPendingShipQty(Integer pendingShipQty) { this.pendingShipQty = pendingShipQty; }
    public Integer getFbaStock() { return fbaStock; }
    public void setFbaStock(Integer fbaStock) { this.fbaStock = fbaStock; }
    public Integer getFbaInbound() { return fbaInbound; }
    public void setFbaInbound(Integer fbaInbound) { this.fbaInbound = fbaInbound; }
    public Integer getTotalInventory() { return totalInventory; }
    public void setTotalInventory(Integer totalInventory) { this.totalInventory = totalInventory; }
    public Integer getSales7d() { return sales7d; }
    public void setSales7d(Integer sales7d) { this.sales7d = sales7d; }
    public Integer getSales14d() { return sales14d; }
    public void setSales14d(Integer sales14d) { this.sales14d = sales14d; }
    public Integer getSales30d() { return sales30d; }
    public void setSales30d(Integer sales30d) { this.sales30d = sales30d; }
    public Integer getSales60d() { return sales60d; }
    public void setSales60d(Integer sales60d) { this.sales60d = sales60d; }
    public BigDecimal getSalesSpeed14d() { return salesSpeed14d; }
    public void setSalesSpeed14d(BigDecimal salesSpeed14d) { this.salesSpeed14d = salesSpeed14d; }
    public BigDecimal getSalesSpeed30d() { return salesSpeed30d; }
    public void setSalesSpeed30d(BigDecimal salesSpeed30d) { this.salesSpeed30d = salesSpeed30d; }
    public BigDecimal getSalesSpeed60d() { return salesSpeed60d; }
    public void setSalesSpeed60d(BigDecimal salesSpeed60d) { this.salesSpeed60d = salesSpeed60d; }
    public BigDecimal getAvgMonthlySales() { return avgMonthlySales; }
    public void setAvgMonthlySales(BigDecimal avgMonthlySales) { this.avgMonthlySales = avgMonthlySales; }
    public BigDecimal getSafetyStock() { return safetyStock; }
    public void setSafetyStock(BigDecimal safetyStock) { this.safetyStock = safetyStock; }
    public BigDecimal getShipQty() { return shipQty; }
    public void setShipQty(BigDecimal shipQty) { this.shipQty = shipQty; }
    public BigDecimal getReplenishQty() { return replenishQty; }
    public void setReplenishQty(BigDecimal replenishQty) { this.replenishQty = replenishQty; }
    public BigDecimal getRestockDays() { return restockDays; }
    public void setRestockDays(BigDecimal restockDays) { this.restockDays = restockDays; }
	public String getRegionGroup() { return regionGroup; }
	public void setRegionGroup(String regionGroup) { this.regionGroup = regionGroup; }
    public Date getCalcTime() { return calcTime; }
    public void setCalcTime(Date calcTime) { this.calcTime = calcTime; }
    public String getSortField() { return sortField; }
    public void setSortField(String sortField) { this.sortField = sortField; }
    public String getSortOrder() { return sortOrder; }
    public void setSortOrder(String sortOrder) { this.sortOrder = sortOrder; }
}
