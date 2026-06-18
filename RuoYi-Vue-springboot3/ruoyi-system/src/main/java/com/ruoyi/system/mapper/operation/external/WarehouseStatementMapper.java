package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import com.ruoyi.system.domain.operation.external.WarehouseStatement;

public interface WarehouseStatementMapper
{
    List<WarehouseStatement> selectAll();
    List<WarehouseStatement> selectByType(Integer type);
}
