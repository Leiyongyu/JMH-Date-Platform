package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.util.Date;

/**
 * eBay销量表
 */
public class EbaySales implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String platformOrderNo;
    private String currency;
    private String sku;
    private Integer quantity;
    private Date paymentTime;
    private Date uploadTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getPlatformOrderNo() { return platformOrderNo; }
    public void setPlatformOrderNo(String platformOrderNo) { this.platformOrderNo = platformOrderNo; }
    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
    public Date getPaymentTime() { return paymentTime; }
    public void setPaymentTime(Date paymentTime) { this.paymentTime = paymentTime; }
    public Date getUploadTime() { return uploadTime; }
    public void setUploadTime(Date uploadTime) { this.uploadTime = uploadTime; }
}
