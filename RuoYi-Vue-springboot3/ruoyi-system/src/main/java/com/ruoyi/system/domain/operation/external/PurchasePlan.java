package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.util.Date;

/**
 * 采购计划(全字段) (领星)
 */
public class PurchasePlan implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String planSn;
    private String ppgSn;
    private String productName;
    private String sku;
    private String statusText;
    private Integer status;
    private Integer wid;
    private String warehouseName;
    private Integer quantityPlan;
    private Date createTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getPlanSn() { return planSn; }
    public void setPlanSn(String planSn) { this.planSn = planSn; }
    public String getPpgSn() { return ppgSn; }
    public void setPpgSn(String ppgSn) { this.ppgSn = ppgSn; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getStatusText() { return statusText; }
    public void setStatusText(String statusText) { this.statusText = statusText; }
    public Integer getStatus() { return status; }
    public void setStatus(Integer status) { this.status = status; }
    public Integer getWid() { return wid; }
    public void setWid(Integer wid) { this.wid = wid; }
    public String getWarehouseName() { return warehouseName; }
    public void setWarehouseName(String warehouseName) { this.warehouseName = warehouseName; }
    public Integer getQuantityPlan() { return quantityPlan; }
    public void setQuantityPlan(Integer quantityPlan) { this.quantityPlan = quantityPlan; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
}
