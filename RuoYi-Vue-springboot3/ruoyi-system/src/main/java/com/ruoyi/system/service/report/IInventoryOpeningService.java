package com.ruoyi.system.service.report;

import com.ruoyi.system.domain.report.InventoryOpeningValue;
import java.util.List;

public interface IInventoryOpeningService
{
    List<InventoryOpeningValue> selectList(InventoryOpeningValue vo);
}
