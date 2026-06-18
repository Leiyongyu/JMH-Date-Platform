package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import com.ruoyi.system.domain.operation.external.PurchasePlan;

public interface PurchasePlanMapper
{
    List<PurchasePlan> selectAll();
    List<PurchasePlan> selectByStatusText(String statusText);
}
