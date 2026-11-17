package com.ruoyi.system.domain.operation.customs;

import java.io.Serializable;
import java.util.List;
import java.util.Map;

public class CustomsStockOrderLinkRequest implements Serializable
{
    private static final long serialVersionUID = 1L;

    private List<String> overseasOrderNos;
    private List<String> stockSkuKeys;
    private List<String> shipmentIds;
    private List<String> fbaSkuKeys;
    private Map<String, Integer> taxOverrides;

    public List<String> getOverseasOrderNos() { return overseasOrderNos; }
    public void setOverseasOrderNos(List<String> overseasOrderNos) { this.overseasOrderNos = overseasOrderNos; }
    public List<String> getStockSkuKeys() { return stockSkuKeys; }
    public void setStockSkuKeys(List<String> stockSkuKeys) { this.stockSkuKeys = stockSkuKeys; }
    public List<String> getShipmentIds() { return shipmentIds; }
    public void setShipmentIds(List<String> shipmentIds) { this.shipmentIds = shipmentIds; }
    public List<String> getFbaSkuKeys() { return fbaSkuKeys; }
    public void setFbaSkuKeys(List<String> fbaSkuKeys) { this.fbaSkuKeys = fbaSkuKeys; }
    public Map<String, Integer> getTaxOverrides() { return taxOverrides; }
    public void setTaxOverrides(Map<String, Integer> taxOverrides) { this.taxOverrides = taxOverrides; }
}
