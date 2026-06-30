package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

/** eBay补货公式配置 */
public class EbayReplenishFormula implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private String name;
    private Integer scenarioOrder;
    private Integer productNature;
    private String ruleGroup;
    private String conditionDesc;
    private String compareMetric;
    private BigDecimal lowerBound;
    private BigDecimal upperBound;
    private BigDecimal weight7d;
    private BigDecimal weight15d;
    private BigDecimal weight30d;
    private BigDecimal multiplier;
    private Integer multiply30;
    private Integer status;
    private String remark;
    private Date createTime;
    private Date updateTime;

    public Long getId() { return id; }
    public void setId(Long v) { this.id = v; }
    public String getName() { return name; }
    public void setName(String v) { this.name = v; }
    public Integer getScenarioOrder() { return scenarioOrder; }
    public void setScenarioOrder(Integer v) { this.scenarioOrder = v; }
    public Integer getProductNature() { return productNature; }
    public void setProductNature(Integer v) { this.productNature = v; }
    public String getRuleGroup() { return ruleGroup; }
    public void setRuleGroup(String v) { this.ruleGroup = v; }
    public String getConditionDesc() { return conditionDesc; }
    public void setConditionDesc(String v) { this.conditionDesc = v; }
    public String getCompareMetric() { return compareMetric; }
    public void setCompareMetric(String v) { this.compareMetric = v; }
    public BigDecimal getLowerBound() { return lowerBound; }
    public void setLowerBound(BigDecimal v) { this.lowerBound = v; }
    public BigDecimal getUpperBound() { return upperBound; }
    public void setUpperBound(BigDecimal v) { this.upperBound = v; }
    public BigDecimal getWeight7d() { return weight7d; }
    public void setWeight7d(BigDecimal v) { this.weight7d = v; }
    public BigDecimal getWeight15d() { return weight15d; }
    public void setWeight15d(BigDecimal v) { this.weight15d = v; }
    public BigDecimal getWeight30d() { return weight30d; }
    public void setWeight30d(BigDecimal v) { this.weight30d = v; }
    public BigDecimal getMultiplier() { return multiplier; }
    public void setMultiplier(BigDecimal v) { this.multiplier = v; }
    public Integer getMultiply30() { return multiply30; }
    public void setMultiply30(Integer v) { this.multiply30 = v; }
    public Integer getStatus() { return status; }
    public void setStatus(Integer v) { this.status = v; }
    public String getRemark() { return remark; }
    public void setRemark(String v) { this.remark = v; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date v) { this.createTime = v; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date v) { this.updateTime = v; }
}
