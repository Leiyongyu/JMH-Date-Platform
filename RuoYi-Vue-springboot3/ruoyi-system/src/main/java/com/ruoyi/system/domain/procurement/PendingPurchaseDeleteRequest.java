package com.ruoyi.system.domain.procurement;

import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;

/** 批量删除使用请求体，避免大量ID超过URL长度限制。 */
public class PendingPurchaseDeleteRequest
{
    @NotEmpty(message = "请选择需要删除的待采购记录")
    @Size(max = 5000, message = "单次最多删除5000条待采购记录")
    private List<@NotNull(message = "删除记录ID不能为空") @Positive(message = "删除记录ID必须大于0") Long> ids;

    public List<Long> getIds() { return ids; }
    public void setIds(List<Long> ids) { this.ids = ids; }
}

