package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.math.BigDecimal;

public class CustomsDeclarationItem extends CustomsProduct implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Integer quantity;
    private Integer boxCount;
    private String sourceOrderNo;
    private String declarationSourceType;
    private String sourceLineId;
    private String rawSku;
    private String warehouseBucket;
    private String warehouseName;
    private String matchStatus;
    /** 来源 SKU 是否命中出入库清单。 */
    private Boolean inventoryMatched;
    /** 来源 SKU 是否具备可用于报关的商品资料。 */
    private Boolean productMatched;
    private BigDecimal orderTotalCbm;
    private BigDecimal totalPrice;
    private BigDecimal totalWeight;

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
    public Integer getBoxCount() { return boxCount; }
    public void setBoxCount(Integer boxCount) { this.boxCount = boxCount; }
    public String getSourceOrderNo() { return sourceOrderNo; }
    public void setSourceOrderNo(String sourceOrderNo) { this.sourceOrderNo = sourceOrderNo; }
    public String getDeclarationSourceType() { return declarationSourceType; }
    public void setDeclarationSourceType(String declarationSourceType) { this.declarationSourceType = declarationSourceType; }
    public String getSourceLineId() { return sourceLineId; }
    public void setSourceLineId(String sourceLineId) { this.sourceLineId = sourceLineId; }
    public String getRawSku() { return rawSku; }
    public void setRawSku(String rawSku) { this.rawSku = rawSku; }
    public String getWarehouseBucket() { return warehouseBucket; }
    public void setWarehouseBucket(String warehouseBucket) { this.warehouseBucket = warehouseBucket; }
    public String getWarehouseName() { return warehouseName; }
    public void setWarehouseName(String warehouseName) { this.warehouseName = warehouseName; }
    public String getMatchStatus() { return matchStatus; }
    public void setMatchStatus(String matchStatus) { this.matchStatus = matchStatus; }
    public Boolean getInventoryMatched() { return inventoryMatched; }
    public void setInventoryMatched(Boolean inventoryMatched) { this.inventoryMatched = inventoryMatched; }
    public Boolean getProductMatched() { return productMatched; }
    public void setProductMatched(Boolean productMatched) { this.productMatched = productMatched; }
    public BigDecimal getOrderTotalCbm() { return orderTotalCbm; }
    public void setOrderTotalCbm(BigDecimal orderTotalCbm) { this.orderTotalCbm = orderTotalCbm; }
    public BigDecimal getTotalPrice() { return totalPrice; }
    public void setTotalPrice(BigDecimal totalPrice) { this.totalPrice = totalPrice; }
    public BigDecimal getTotalWeight() { return totalWeight; }
    public void setTotalWeight(BigDecimal totalWeight) { this.totalWeight = totalWeight; }
}
