package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import com.ruoyi.system.domain.operation.external.Warehouse;

public interface WarehouseMapper
{
    List<Warehouse> selectAll();
    Warehouse selectByWid(Integer wid);
}
