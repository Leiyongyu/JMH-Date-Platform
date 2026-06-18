package com.ruoyi.system.domain.operation.external;

import java.io.Serializable;
import java.math.BigDecimal;

/**
 * 仓库库存明细表 (领星)
 */
public class WarehouseInventoryDetail implements Serializable
{
    private static final long serialVersionUID = 1L;

    private Long id;
    private String wid;
    private String productId;
    private String sku;
    private String sellerId;
    private String fnsku;
    private String productTotal;
    private String productValidNum;
    private String productBadNum;
    private String productQcNum;
    private String productLockNum;
    private Integer goodLockNum;
    private Integer badLockNum;
    private String stockCostTotal;
    private String quantityReceive;
    private String stockCost;
    private String productOnway;
    private String transitHeadCost;
    private String averageAge;
    private Integer expectValidNum;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getWid() { return wid; }
    public void setWid(String wid) { this.wid = wid; }
    public String getProductId() { return productId; }
    public void setProductId(String productId) { this.productId = productId; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getSellerId() { return sellerId; }
    public void setSellerId(String sellerId) { this.sellerId = sellerId; }
    public String getFnsku() { return fnsku; }
    public void setFnsku(String fnsku) { this.fnsku = fnsku; }

    public Integer getProductValidNum() { return parseOrNull(productValidNum); }
    public void setProductValidNum(String productValidNum) { this.productValidNum = productValidNum; }
    public Integer getProductLockNum() { return parseOrNull(productLockNum); }
    public void setProductLockNum(String productLockNum) { this.productLockNum = productLockNum; }
    public Integer getProductOnway() { return parseOrNull(productOnway); }
    public void setProductOnway(String productOnway) { this.productOnway = productOnway; }
    public Integer getQuantityReceive() { return parseOrNull(quantityReceive); }
    public void setQuantityReceive(String quantityReceive) { this.quantityReceive = quantityReceive; }

    private Integer parseOrNull(String val) {
        if (val == null || val.isEmpty()) return 0;
        try { return Integer.parseInt(val); } catch (NumberFormatException e) { return 0; }
    }
}
