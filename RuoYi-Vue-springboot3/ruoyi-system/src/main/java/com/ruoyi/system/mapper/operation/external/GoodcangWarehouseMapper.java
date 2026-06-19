package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import org.apache.ibatis.annotations.Param;
import com.ruoyi.system.domain.operation.external.GoodcangWarehouse;

public interface GoodcangWarehouseMapper
{
    List<GoodcangWarehouse> selectAll();
    List<GoodcangWarehouse> selectByWarehouseCodes(List<String> warehouseCodes);
    int deleteAll();
    int batchInsert(@Param("list") List<GoodcangWarehouse> list);
}
