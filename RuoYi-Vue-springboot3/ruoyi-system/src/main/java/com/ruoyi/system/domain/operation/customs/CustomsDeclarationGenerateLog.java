package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.math.BigDecimal;
import java.time.LocalDateTime;

public class CustomsDeclarationGenerateLog implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String declarationNo;
    private String sourceType;
    private String sourceOrderNo;
    private String sourceLineId;
    private String rawSku;
    private String standardSku;
    private String productCode;
    private String sourceLocation;
    private String warehouseBucket;
    private String warehouseName;
    private BigDecimal quantity;
    private String matchStatus;
    private String remark;
    private String createdBy;
    private LocalDateTime createdTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getDeclarationNo() { return declarationNo; }
    public void setDeclarationNo(String declarationNo) { this.declarationNo = declarationNo; }
    public String getSourceType() { return sourceType; }
    public void setSourceType(String sourceType) { this.sourceType = sourceType; }
    public String getSourceOrderNo() { return sourceOrderNo; }
    public void setSourceOrderNo(String sourceOrderNo) { this.sourceOrderNo = sourceOrderNo; }
    public String getSourceLineId() { return sourceLineId; }
    public void setSourceLineId(String sourceLineId) { this.sourceLineId = sourceLineId; }
    public String getRawSku() { return rawSku; }
    public void setRawSku(String rawSku) { this.rawSku = rawSku; }
    public String getStandardSku() { return standardSku; }
    public void setStandardSku(String standardSku) { this.standardSku = standardSku; }
    public String getProductCode() { return productCode; }
    public void setProductCode(String productCode) { this.productCode = productCode; }
    public String getSourceLocation() { return sourceLocation; }
    public void setSourceLocation(String sourceLocation) { this.sourceLocation = sourceLocation; }
    public String getWarehouseBucket() { return warehouseBucket; }
    public void setWarehouseBucket(String warehouseBucket) { this.warehouseBucket = warehouseBucket; }
    public String getWarehouseName() { return warehouseName; }
    public void setWarehouseName(String warehouseName) { this.warehouseName = warehouseName; }
    public BigDecimal getQuantity() { return quantity; }
    public void setQuantity(BigDecimal quantity) { this.quantity = quantity; }
    public String getMatchStatus() { return matchStatus; }
    public void setMatchStatus(String matchStatus) { this.matchStatus = matchStatus; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
    public String getCreatedBy() { return createdBy; }
    public void setCreatedBy(String createdBy) { this.createdBy = createdBy; }
    public LocalDateTime getCreatedTime() { return createdTime; }
    public void setCreatedTime(LocalDateTime createdTime) { this.createdTime = createdTime; }
}
