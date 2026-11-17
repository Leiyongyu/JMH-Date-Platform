package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import org.apache.ibatis.annotations.Param;
import com.ruoyi.system.domain.operation.external.WarehouseStatement;

public interface WarehouseStatementMapper
{
    List<WarehouseStatement> selectAll();
    List<WarehouseStatement> selectByType(Integer type);
    int insert(WarehouseStatement entity);
    int updateById(WarehouseStatement entity);
    WarehouseStatement selectByUniqueKey(@Param("wid") Integer wid, @Param("sku") String sku, @Param("optTime") String optTime);
}
