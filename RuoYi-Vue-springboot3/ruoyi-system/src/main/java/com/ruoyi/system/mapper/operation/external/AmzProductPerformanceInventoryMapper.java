package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzProductPerformanceInventory;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface AmzProductPerformanceInventoryMapper
{
    int deleteAll();

    int batchInsert(@Param("list") List<AmzProductPerformanceInventory> list);
}
