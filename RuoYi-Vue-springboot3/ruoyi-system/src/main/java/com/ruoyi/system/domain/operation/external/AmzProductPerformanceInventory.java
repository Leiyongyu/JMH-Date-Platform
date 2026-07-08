package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;

/** 领星产品表现接口中的 Amazon FBA 库存口径。 */
public class AmzProductPerformanceInventory implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private Integer sid;
    private String sellerSku;
    private String localSku;
    private Integer fbaFulfillable;
    private Integer fbaTransfer;
    private Integer fbaReceiving;
    private Integer fbaReserved;
    private Integer fbaInbound;
    private Integer fbaInboundWorking;
    private Integer fbaStock;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Integer getSid() { return sid; }
    public void setSid(Integer sid) { this.sid = sid; }
    public String getSellerSku() { return sellerSku; }
    public void setSellerSku(String sellerSku) { this.sellerSku = sellerSku; }
    public String getLocalSku() { return localSku; }
    public void setLocalSku(String localSku) { this.localSku = localSku; }
    public Integer getFbaFulfillable() { return fbaFulfillable; }
    public void setFbaFulfillable(Integer fbaFulfillable) { this.fbaFulfillable = fbaFulfillable; }
    public Integer getFbaTransfer() { return fbaTransfer; }
    public void setFbaTransfer(Integer fbaTransfer) { this.fbaTransfer = fbaTransfer; }
    public Integer getFbaReceiving() { return fbaReceiving; }
    public void setFbaReceiving(Integer fbaReceiving) { this.fbaReceiving = fbaReceiving; }
    public Integer getFbaReserved() { return fbaReserved; }
    public void setFbaReserved(Integer fbaReserved) { this.fbaReserved = fbaReserved; }
    public Integer getFbaInbound() { return fbaInbound; }
    public void setFbaInbound(Integer fbaInbound) { this.fbaInbound = fbaInbound; }
    public Integer getFbaInboundWorking() { return fbaInboundWorking; }
    public void setFbaInboundWorking(Integer fbaInboundWorking) { this.fbaInboundWorking = fbaInboundWorking; }
    public Integer getFbaStock() { return fbaStock; }
    public void setFbaStock(Integer fbaStock) { this.fbaStock = fbaStock; }
}
