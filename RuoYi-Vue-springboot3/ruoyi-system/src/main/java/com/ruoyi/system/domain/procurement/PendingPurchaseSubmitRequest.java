package com.ruoyi.system.domain.procurement;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** eBay补货2.0采购确认参数。 */
public class PendingPurchaseSubmitRequest
{
    @NotBlank(message = "站点不能为空")
    @Size(max = 100, message = "站点长度不能超过100个字符")
    private String site;

    @NotBlank(message = "SKU不能为空")
    @Size(max = 255, message = "SKU长度不能超过255个字符")
    private String sku;

    @NotNull(message = "最终采购量不能为空")
    @Min(value = 1, message = "最终采购量必须大于0")
    private Integer purchaseQuantity;

    public String getSite() { return site; }
    public void setSite(String site) { this.site = site; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public Integer getPurchaseQuantity() { return purchaseQuantity; }
    public void setPurchaseQuantity(Integer purchaseQuantity) { this.purchaseQuantity = purchaseQuantity; }
}
