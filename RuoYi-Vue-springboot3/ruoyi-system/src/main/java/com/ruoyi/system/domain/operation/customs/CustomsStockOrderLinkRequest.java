package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.util.List;

public class CustomsStockOrderLinkRequest implements Serializable
{
    private static final long serialVersionUID = 1L;

    private List<String> overseasOrderNos;
    private List<String> shipmentIds;

    public List<String> getOverseasOrderNos() { return overseasOrderNos; }
    public void setOverseasOrderNos(List<String> overseasOrderNos) { this.overseasOrderNos = overseasOrderNos; }
    public List<String> getShipmentIds() { return shipmentIds; }
    public void setShipmentIds(List<String> shipmentIds) { this.shipmentIds = shipmentIds; }
}
