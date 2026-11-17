package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

/** 领星备货单详情 */
public class OverseasStockOrderDetail implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String overseasOrderNo;
    private Integer sWid;
    private Integer rWid;
    private Integer status;
    private String productCode;
    private String sku;
    private String sellerId;
    private Integer packageNum;
    private String tariffsCurrencyUnit;
    private Integer boxType;
    private String boxSku;
    private String boxThirdPartyProductName;
    private String boxThirdPartyProductCode;
    private String boxSellerId;
    private String boxRange;
    private Integer boxNumber;
    private BigDecimal cgBoxWeight;
    private BigDecimal cgBoxLength;
    private BigDecimal cgBoxWidth;
    private BigDecimal cgBoxHeight;
    private Integer quantityInCase;
    private BigDecimal boxCbm;
    private BigDecimal totalBoxVolume;
    private BigDecimal totalBoxWeight;
    private BigDecimal totalBoxVolumeWeight;
    private String boxRemark;
    private Integer orderTotalBoxNum;
    private BigDecimal orderTotalBoxWeight;
    private BigDecimal orderTotalBoxVolume;
    private BigDecimal orderTotalBoxVolumeWeight;
    private Date createTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getOverseasOrderNo() { return overseasOrderNo; }
    public void setOverseasOrderNo(String v) { this.overseasOrderNo = v; }
    public Integer getSWid() { return sWid; }
    public void setSWid(Integer v) { this.sWid = v; }
    public Integer getRWid() { return rWid; }
    public void setRWid(Integer v) { this.rWid = v; }
    public Integer getStatus() { return status; }
    public void setStatus(Integer v) { this.status = v; }
    public String getProductCode() { return productCode; }
    public void setProductCode(String v) { this.productCode = v; }
    public String getSku() { return sku; }
    public void setSku(String v) { this.sku = v; }
    public String getSellerId() { return sellerId; }
    public void setSellerId(String v) { this.sellerId = v; }
    public Integer getPackageNum() { return packageNum; }
    public void setPackageNum(Integer v) { this.packageNum = v; }
    public String getTariffsCurrencyUnit() { return tariffsCurrencyUnit; }
    public void setTariffsCurrencyUnit(String v) { this.tariffsCurrencyUnit = v; }
    public Integer getBoxType() { return boxType; }
    public void setBoxType(Integer v) { this.boxType = v; }
    public String getBoxSku() { return boxSku; }
    public void setBoxSku(String v) { this.boxSku = v; }
    public String getBoxThirdPartyProductName() { return boxThirdPartyProductName; }
    public void setBoxThirdPartyProductName(String v) { this.boxThirdPartyProductName = v; }
    public String getBoxThirdPartyProductCode() { return boxThirdPartyProductCode; }
    public void setBoxThirdPartyProductCode(String v) { this.boxThirdPartyProductCode = v; }
    public String getBoxSellerId() { return boxSellerId; }
    public void setBoxSellerId(String v) { this.boxSellerId = v; }
    public String getBoxRange() { return boxRange; }
    public void setBoxRange(String v) { this.boxRange = v; }
    public Integer getBoxNumber() { return boxNumber; }
    public void setBoxNumber(Integer v) { this.boxNumber = v; }
    public BigDecimal getCgBoxWeight() { return cgBoxWeight; }
    public void setCgBoxWeight(BigDecimal v) { this.cgBoxWeight = v; }
    public BigDecimal getCgBoxLength() { return cgBoxLength; }
    public void setCgBoxLength(BigDecimal v) { this.cgBoxLength = v; }
    public BigDecimal getCgBoxWidth() { return cgBoxWidth; }
    public void setCgBoxWidth(BigDecimal v) { this.cgBoxWidth = v; }
    public BigDecimal getCgBoxHeight() { return cgBoxHeight; }
    public void setCgBoxHeight(BigDecimal v) { this.cgBoxHeight = v; }
    public Integer getQuantityInCase() { return quantityInCase; }
    public void setQuantityInCase(Integer v) { this.quantityInCase = v; }
    public BigDecimal getBoxCbm() { return boxCbm; }
    public void setBoxCbm(BigDecimal v) { this.boxCbm = v; }
    public BigDecimal getTotalBoxVolume() { return totalBoxVolume; }
    public void setTotalBoxVolume(BigDecimal v) { this.totalBoxVolume = v; }
    public BigDecimal getTotalBoxWeight() { return totalBoxWeight; }
    public void setTotalBoxWeight(BigDecimal v) { this.totalBoxWeight = v; }
    public BigDecimal getTotalBoxVolumeWeight() { return totalBoxVolumeWeight; }
    public void setTotalBoxVolumeWeight(BigDecimal v) { this.totalBoxVolumeWeight = v; }
    public String getBoxRemark() { return boxRemark; }
    public void setBoxRemark(String v) { this.boxRemark = v; }
    public Integer getOrderTotalBoxNum() { return orderTotalBoxNum; }
    public void setOrderTotalBoxNum(Integer v) { this.orderTotalBoxNum = v; }
    public BigDecimal getOrderTotalBoxWeight() { return orderTotalBoxWeight; }
    public void setOrderTotalBoxWeight(BigDecimal v) { this.orderTotalBoxWeight = v; }
    public BigDecimal getOrderTotalBoxVolume() { return orderTotalBoxVolume; }
    public void setOrderTotalBoxVolume(BigDecimal v) { this.orderTotalBoxVolume = v; }
    public BigDecimal getOrderTotalBoxVolumeWeight() { return orderTotalBoxVolumeWeight; }
    public void setOrderTotalBoxVolumeWeight(BigDecimal v) { this.orderTotalBoxVolumeWeight = v; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date v) { this.createTime = v; }
}
