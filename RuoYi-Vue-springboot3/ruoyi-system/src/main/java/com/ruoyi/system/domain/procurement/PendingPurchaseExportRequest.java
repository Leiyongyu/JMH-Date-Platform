package com.ruoyi.system.domain.procurement;

import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/** 待采购记录导出参数。 */
public class PendingPurchaseExportRequest
{
    @NotEmpty(message = "请选择需要导出的待采购记录")
    @Size(max = 5000, message = "单次最多导出5000条待采购记录")
    private List<@NotNull(message = "导出记录ID不能为空") Long> ids;

    public List<Long> getIds() { return ids; }
    public void setIds(List<Long> ids) { this.ids = ids; }
}
