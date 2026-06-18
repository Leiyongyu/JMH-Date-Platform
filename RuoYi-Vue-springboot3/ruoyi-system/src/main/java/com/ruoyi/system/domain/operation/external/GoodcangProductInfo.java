package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;

/**
 * 谷仓商品信息表
 */
public class GoodcangProductInfo implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String skuMiddle;
    private String productNameCn;
    private BigDecimal realWeight;
    private BigDecimal realLength;
    private BigDecimal realWidth;
    private BigDecimal realHeight;
    private BigDecimal volume;
    private BigDecimal price;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSkuMiddle() { return skuMiddle; }
    public void setSkuMiddle(String skuMiddle) { this.skuMiddle = skuMiddle; }
    public String getProductNameCn() { return productNameCn; }
    public void setProductNameCn(String productNameCn) { this.productNameCn = productNameCn; }
    public BigDecimal getRealWeight() { return realWeight; }
    public void setRealWeight(BigDecimal realWeight) { this.realWeight = realWeight; }
    public BigDecimal getRealLength() { return realLength; }
    public void setRealLength(BigDecimal realLength) { this.realLength = realLength; }
    public BigDecimal getRealWidth() { return realWidth; }
    public void setRealWidth(BigDecimal realWidth) { this.realWidth = realWidth; }
    public BigDecimal getRealHeight() { return realHeight; }
    public void setRealHeight(BigDecimal realHeight) { this.realHeight = realHeight; }
    public BigDecimal getVolume() { return volume; }
    public void setVolume(BigDecimal volume) { this.volume = volume; }
    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }
}
