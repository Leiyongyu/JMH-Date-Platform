package com.ruoyi.system.domain.operation;

import java.math.BigDecimal;
import java.util.Date;
import com.fasterxml.jackson.annotation.JsonFormat;
import com.ruoyi.common.annotation.Excel;
import com.ruoyi.common.core.domain.BaseEntity;

public class EbayReplenishmentSnapshot extends BaseEntity
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

    private Integer productNature;

    @Excel(name = "近30天利润")
    private BigDecimal profitRate30d;

    @Excel(name = "退货率")
    private BigDecimal returnRate;

    @Excel(name = "海外在途")
    private Integer overseasOnway;

    @Excel(name = "海外可售")
    private Integer overseasSellable;

    @Excel(name = "海外总库存")
    private Integer overseasTotal;

    @Excel(name = "采购待交付")
    private Integer purchasePendingDelivery;

    @Excel(name = "成都可售")
    private Integer localSellable;

    @Excel(name = "成都在途")
    private Integer localOnway;

    @Excel(name = "采购计划")
    private Integer purchasePlanQty;

    @Excel(name = "待出库")
    private Integer lockedQty;

    @Excel(name = "总库存")
    private Integer totalInventory;

    @Excel(name = "近7天销量")
    private Integer sales7d;

    @Excel(name = "近15天销量")
    private Integer sales15d;

    @Excel(name = "近30天销量")
    private Integer sales30d;

    @Excel(name = "近90天销量")
    private Integer sales90d;

    @Excel(name = "历史最大月销")
    private Integer maxMonthlySales;

    @Excel(name = "海外在库库销比")
    private BigDecimal overseasSellableSalesRatio;

    @Excel(name = "海外总库销比")
    private BigDecimal overseasTotalSalesRatio;

    @Excel(name = "总库存库销比")
    private BigDecimal totalInventorySalesRatio;

    @Excel(name = "最近本地出库时间")
    private String lastLocalOutboundTime;

    @Excel(name = "出库天数")
    private Integer outboundDays;

    @Excel(name = "采购周期")
    private Integer purchaseCycleDays;

    @Excel(name = "采购数量")
    private BigDecimal suggestPurchaseQty;

    @Excel(name = "最大月销补货量")
    private Integer maxMonthlyReplenishQty;

    @Excel(name = "退货等级")
    private String returnLevel;

    @Excel(name = "月动销率")
    private BigDecimal monthlyTurnoverRate;

    @Excel(name = "负责人")
    private String ownerName;

    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private Date calcTime;

    private String sortField;
    private String sortOrder;

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
    public Integer getProductNature() { return productNature; }
    public void setProductNature(Integer v) { this.productNature = v; }
    public BigDecimal getProfitRate30d() { return profitRate30d; }
    public void setProfitRate30d(BigDecimal profitRate30d) { this.profitRate30d = profitRate30d; }
    public BigDecimal getReturnRate() { return returnRate; }
    public void setReturnRate(BigDecimal returnRate) { this.returnRate = returnRate; }
    public Integer getOverseasOnway() { return overseasOnway; }
    public void setOverseasOnway(Integer overseasOnway) { this.overseasOnway = overseasOnway; }
    public Integer getOverseasSellable() { return overseasSellable; }
    public void setOverseasSellable(Integer overseasSellable) { this.overseasSellable = overseasSellable; }
    public Integer getOverseasTotal() { return overseasTotal; }
    public void setOverseasTotal(Integer overseasTotal) { this.overseasTotal = overseasTotal; }
    public Integer getPurchasePendingDelivery() { return purchasePendingDelivery; }
    public void setPurchasePendingDelivery(Integer purchasePendingDelivery) { this.purchasePendingDelivery = purchasePendingDelivery; }
    public Integer getLocalSellable() { return localSellable; }
    public void setLocalSellable(Integer localSellable) { this.localSellable = localSellable; }
    public Integer getLocalOnway() { return localOnway; }
    public void setLocalOnway(Integer localOnway) { this.localOnway = localOnway; }
    public Integer getPurchasePlanQty() { return purchasePlanQty; }
    public void setPurchasePlanQty(Integer purchasePlanQty) { this.purchasePlanQty = purchasePlanQty; }
    public Integer getLockedQty() { return lockedQty; }
    public void setLockedQty(Integer lockedQty) { this.lockedQty = lockedQty; }
    public Integer getTotalInventory() { return totalInventory; }
    public void setTotalInventory(Integer totalInventory) { this.totalInventory = totalInventory; }
    public Integer getSales7d() { return sales7d; }
    public void setSales7d(Integer sales7d) { this.sales7d = sales7d; }
    public Integer getSales15d() { return sales15d; }
    public void setSales15d(Integer v) { this.sales15d = v; }
    public Integer getSales30d() { return sales30d; }
    public void setSales30d(Integer sales30d) { this.sales30d = sales30d; }
    public Integer getSales90d() { return sales90d; }
    public void setSales90d(Integer sales90d) { this.sales90d = sales90d; }
    public Integer getMaxMonthlySales() { return maxMonthlySales; }
    public void setMaxMonthlySales(Integer maxMonthlySales) { this.maxMonthlySales = maxMonthlySales; }
    public BigDecimal getOverseasSellableSalesRatio() { return overseasSellableSalesRatio; }
    public void setOverseasSellableSalesRatio(BigDecimal overseasSellableSalesRatio) { this.overseasSellableSalesRatio = overseasSellableSalesRatio; }
    public BigDecimal getOverseasTotalSalesRatio() { return overseasTotalSalesRatio; }
    public void setOverseasTotalSalesRatio(BigDecimal overseasTotalSalesRatio) { this.overseasTotalSalesRatio = overseasTotalSalesRatio; }
    public BigDecimal getTotalInventorySalesRatio() { return totalInventorySalesRatio; }
    public void setTotalInventorySalesRatio(BigDecimal totalInventorySalesRatio) { this.totalInventorySalesRatio = totalInventorySalesRatio; }
    public String getLastLocalOutboundTime() { return lastLocalOutboundTime; }
    public void setLastLocalOutboundTime(String lastLocalOutboundTime) { this.lastLocalOutboundTime = lastLocalOutboundTime; }
    public Integer getOutboundDays() { return outboundDays; }
    public void setOutboundDays(Integer outboundDays) { this.outboundDays = outboundDays; }
    public Integer getPurchaseCycleDays() { return purchaseCycleDays; }
    public void setPurchaseCycleDays(Integer purchaseCycleDays) { this.purchaseCycleDays = purchaseCycleDays; }
    public BigDecimal getSuggestPurchaseQty() { return suggestPurchaseQty; }
    public void setSuggestPurchaseQty(BigDecimal suggestPurchaseQty) { this.suggestPurchaseQty = suggestPurchaseQty; }
    public Integer getMaxMonthlyReplenishQty() { return maxMonthlyReplenishQty; }
    public void setMaxMonthlyReplenishQty(Integer maxMonthlyReplenishQty) { this.maxMonthlyReplenishQty = maxMonthlyReplenishQty; }
    public String getReturnLevel() { return returnLevel; }
    public void setReturnLevel(String returnLevel) { this.returnLevel = returnLevel; }
    public BigDecimal getMonthlyTurnoverRate() { return monthlyTurnoverRate; }
    public void setMonthlyTurnoverRate(BigDecimal v) { this.monthlyTurnoverRate = v; }
    public String getOwnerName() { return ownerName; }
    public void setOwnerName(String ownerName) { this.ownerName = ownerName; }
    public Date getCalcTime() { return calcTime; }
    public void setCalcTime(Date calcTime) { this.calcTime = calcTime; }
    public String getSortField() { return sortField; }
    public void setSortField(String sortField) { this.sortField = sortField; }
    public String getSortOrder() { return sortOrder; }
    public void setSortOrder(String sortOrder) { this.sortOrder = sortOrder; }
}
