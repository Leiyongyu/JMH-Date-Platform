package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import org.apache.ibatis.annotations.Param;
import com.ruoyi.system.domain.operation.external.WarehouseInventoryDetail;

public interface WarehouseInventoryDetailMapper
{
    List<WarehouseInventoryDetail> selectAll();
    List<WarehouseInventoryDetail> selectByWids(List<String> wids);
    int deleteAll();
    int batchInsert(@Param("list") List<WarehouseInventoryDetail> list);
}
