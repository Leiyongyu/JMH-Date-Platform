package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

public class AmzFormulaConfig implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String regionGroup;
    private String regionName;
    private String marketplaces;
    private String strategyType;
    private BigDecimal salesWeight14d;
    private BigDecimal salesWeight30d;
    private BigDecimal salesWeight60d;
    private Integer monthMultiplier;
    private Integer safetyDays;
    private Integer shipDays;
    private Integer replenishDays;
    private Integer deductFbaStock;
    private Integer deductFbaInbound;
    private Integer deductDomesticStock;
    private Integer deductPurchasedQty;
    private Integer deductPendingShipQty;
    private Integer allowNegativeReplenish;
    private BigDecimal minReplenishQty;
    private BigDecimal maxReplenishQty;
    private String roundMode;
    private Integer enabled;
    private String remark;
    private String formulaWeightedDaily;
    private String formulaMonthly;
    private String formulaSafety;
    private String formulaShip;
    private String formulaReplenish;
    private String formulaRestock;
    private Date updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getRegionGroup() { return regionGroup; }
    public void setRegionGroup(String regionGroup) { this.regionGroup = regionGroup; }
    public String getRegionName() { return regionName; }
    public void setRegionName(String regionName) { this.regionName = regionName; }
    public String getMarketplaces() { return marketplaces; }
    public void setMarketplaces(String marketplaces) { this.marketplaces = marketplaces; }
    public String getStrategyType() { return strategyType; }
    public void setStrategyType(String strategyType) { this.strategyType = strategyType; }
    public BigDecimal getSalesWeight14d() { return salesWeight14d; }
    public void setSalesWeight14d(BigDecimal v) { this.salesWeight14d = v; }
    public BigDecimal getSalesWeight30d() { return salesWeight30d; }
    public void setSalesWeight30d(BigDecimal v) { this.salesWeight30d = v; }
    public BigDecimal getSalesWeight60d() { return salesWeight60d; }
    public void setSalesWeight60d(BigDecimal v) { this.salesWeight60d = v; }
    public Integer getMonthMultiplier() { return monthMultiplier; }
    public void setMonthMultiplier(Integer v) { this.monthMultiplier = v; }
    public Integer getSafetyDays() { return safetyDays; }
    public void setSafetyDays(Integer v) { this.safetyDays = v; }
    public Integer getShipDays() { return shipDays; }
    public void setShipDays(Integer v) { this.shipDays = v; }
    public Integer getReplenishDays() { return replenishDays; }
    public void setReplenishDays(Integer v) { this.replenishDays = v; }
    public Integer getDeductFbaStock() { return deductFbaStock; }
    public void setDeductFbaStock(Integer deductFbaStock) { this.deductFbaStock = deductFbaStock; }
    public Integer getDeductFbaInbound() { return deductFbaInbound; }
    public void setDeductFbaInbound(Integer deductFbaInbound) { this.deductFbaInbound = deductFbaInbound; }
    public Integer getDeductDomesticStock() { return deductDomesticStock; }
    public void setDeductDomesticStock(Integer deductDomesticStock) { this.deductDomesticStock = deductDomesticStock; }
    public Integer getDeductPurchasedQty() { return deductPurchasedQty; }
    public void setDeductPurchasedQty(Integer deductPurchasedQty) { this.deductPurchasedQty = deductPurchasedQty; }
    public Integer getDeductPendingShipQty() { return deductPendingShipQty; }
    public void setDeductPendingShipQty(Integer deductPendingShipQty) { this.deductPendingShipQty = deductPendingShipQty; }
    public Integer getAllowNegativeReplenish() { return allowNegativeReplenish; }
    public void setAllowNegativeReplenish(Integer allowNegativeReplenish) { this.allowNegativeReplenish = allowNegativeReplenish; }
    public BigDecimal getMinReplenishQty() { return minReplenishQty; }
    public void setMinReplenishQty(BigDecimal minReplenishQty) { this.minReplenishQty = minReplenishQty; }
    public BigDecimal getMaxReplenishQty() { return maxReplenishQty; }
    public void setMaxReplenishQty(BigDecimal maxReplenishQty) { this.maxReplenishQty = maxReplenishQty; }
    public String getRoundMode() { return roundMode; }
    public void setRoundMode(String roundMode) { this.roundMode = roundMode; }
    public Integer getEnabled() { return enabled; }
    public void setEnabled(Integer enabled) { this.enabled = enabled; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
    public String getFormulaWeightedDaily() { return formulaWeightedDaily; }
    public void setFormulaWeightedDaily(String v) { this.formulaWeightedDaily = v; }
    public String getFormulaMonthly() { return formulaMonthly; }
    public void setFormulaMonthly(String v) { this.formulaMonthly = v; }
    public String getFormulaSafety() { return formulaSafety; }
    public void setFormulaSafety(String v) { this.formulaSafety = v; }
    public String getFormulaShip() { return formulaShip; }
    public void setFormulaShip(String v) { this.formulaShip = v; }
    public String getFormulaReplenish() { return formulaReplenish; }
    public void setFormulaReplenish(String v) { this.formulaReplenish = v; }
    public String getFormulaRestock() { return formulaRestock; }
    public void setFormulaRestock(String v) { this.formulaRestock = v; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date updateTime) { this.updateTime = updateTime; }
}
