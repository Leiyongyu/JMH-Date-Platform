package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import com.ruoyi.system.domain.operation.external.WarehouseInventoryDetail;

public interface WarehouseInventoryDetailMapper
{
    List<WarehouseInventoryDetail> selectAll();
    List<WarehouseInventoryDetail> selectByWids(List<String> wids);
}
