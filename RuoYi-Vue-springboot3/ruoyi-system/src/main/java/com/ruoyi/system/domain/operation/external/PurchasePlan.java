package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.util.Date;

/** 采购计划 (领星) */
public class PurchasePlan implements Serializable
{
    private static final long serialVersionUID = 1L;
    private Long id;
    private String planSn;
    private String ppgSn;
    private String productName;
    private String sku;
    private String fnsku;
    private String picUrl;
    private String supplierId;
    private String supplierName;
    private String statusText;
    private Integer status;
    private String sid;
    private String sellerName;
    private String marketplace;
    private String expectArriveTime;
    private String remark;
    private Integer quantityPlan;
    private Integer productId;
    private Integer cgUid;
    private String cgOptUsername;
    private Integer cgBoxPcs;
    private Integer isCombo;
    private Integer isAux;
    private Integer isRelatedProcessPlan;
    private String spu;
    private String spuName;
    private Integer creatorUid;
    private String creatorRealName;
    private Integer wid;
    private String warehouseName;
    private Integer purchaserId;
    private String purchaserName;
    private Date createTime;
    private String planRemark;
    private String attributeJson;
    private String fileJson;
    private String mskuJson;
    private String permUidJson;
    private String permUsernameJson;

    public Long getId() { return id; }
    public void setId(Long v) { this.id = v; }
    public String getPlanSn() { return planSn; }
    public void setPlanSn(String v) { this.planSn = v; }
    public String getPpgSn() { return ppgSn; }
    public void setPpgSn(String v) { this.ppgSn = v; }
    public String getProductName() { return productName; }
    public void setProductName(String v) { this.productName = v; }
    public String getSku() { return sku; }
    public void setSku(String v) { this.sku = v; }
    public String getFnsku() { return fnsku; }
    public void setFnsku(String v) { this.fnsku = v; }
    public String getPicUrl() { return picUrl; }
    public void setPicUrl(String v) { this.picUrl = v; }
    public String getSupplierId() { return supplierId; }
    public void setSupplierId(String v) { this.supplierId = v; }
    public String getSupplierName() { return supplierName; }
    public void setSupplierName(String v) { this.supplierName = v; }
    public String getStatusText() { return statusText; }
    public void setStatusText(String v) { this.statusText = v; }
    public Integer getStatus() { return status; }
    public void setStatus(Integer v) { this.status = v; }
    public String getSid() { return sid; }
    public void setSid(String v) { this.sid = v; }
    public String getSellerName() { return sellerName; }
    public void setSellerName(String v) { this.sellerName = v; }
    public String getMarketplace() { return marketplace; }
    public void setMarketplace(String v) { this.marketplace = v; }
    public String getExpectArriveTime() { return expectArriveTime; }
    public void setExpectArriveTime(String v) { this.expectArriveTime = v; }
    public String getRemark() { return remark; }
    public void setRemark(String v) { this.remark = v; }
    public Integer getQuantityPlan() { return quantityPlan; }
    public void setQuantityPlan(Integer v) { this.quantityPlan = v; }
    public Integer getProductId() { return productId; }
    public void setProductId(Integer v) { this.productId = v; }
    public Integer getCgUid() { return cgUid; }
    public void setCgUid(Integer v) { this.cgUid = v; }
    public String getCgOptUsername() { return cgOptUsername; }
    public void setCgOptUsername(String v) { this.cgOptUsername = v; }
    public Integer getCgBoxPcs() { return cgBoxPcs; }
    public void setCgBoxPcs(Integer v) { this.cgBoxPcs = v; }
    public Integer getIsCombo() { return isCombo; }
    public void setIsCombo(Integer v) { this.isCombo = v; }
    public Integer getIsAux() { return isAux; }
    public void setIsAux(Integer v) { this.isAux = v; }
    public Integer getIsRelatedProcessPlan() { return isRelatedProcessPlan; }
    public void setIsRelatedProcessPlan(Integer v) { this.isRelatedProcessPlan = v; }
    public String getSpu() { return spu; }
    public void setSpu(String v) { this.spu = v; }
    public String getSpuName() { return spuName; }
    public void setSpuName(String v) { this.spuName = v; }
    public Integer getCreatorUid() { return creatorUid; }
    public void setCreatorUid(Integer v) { this.creatorUid = v; }
    public String getCreatorRealName() { return creatorRealName; }
    public void setCreatorRealName(String v) { this.creatorRealName = v; }
    public Integer getWid() { return wid; }
    public void setWid(Integer v) { this.wid = v; }
    public String getWarehouseName() { return warehouseName; }
    public void setWarehouseName(String v) { this.warehouseName = v; }
    public Integer getPurchaserId() { return purchaserId; }
    public void setPurchaserId(Integer v) { this.purchaserId = v; }
    public String getPurchaserName() { return purchaserName; }
    public void setPurchaserName(String v) { this.purchaserName = v; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date v) { this.createTime = v; }
    public String getPlanRemark() { return planRemark; }
    public void setPlanRemark(String v) { this.planRemark = v; }
    public String getAttributeJson() { return attributeJson; }
    public void setAttributeJson(String v) { this.attributeJson = v; }
    public String getFileJson() { return fileJson; }
    public void setFileJson(String v) { this.fileJson = v; }
    public String getMskuJson() { return mskuJson; }
    public void setMskuJson(String v) { this.mskuJson = v; }
    public String getPermUidJson() { return permUidJson; }
    public void setPermUidJson(String v) { this.permUidJson = v; }
    public String getPermUsernameJson() { return permUsernameJson; }
    public void setPermUsernameJson(String v) { this.permUsernameJson = v; }
}
