package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import com.ruoyi.system.domain.operation.external.Warehouse;
import org.apache.ibatis.annotations.Param;

public interface WarehouseMapper
{
    List<Warehouse> selectAll();
    Warehouse selectByWid(Integer wid);

    /** 批量查询（用于同步 upsert 去重） */
    List<Warehouse> selectByWids(@Param("wids") List<Integer> wids);

    /** 单条插入 */
    int insertWarehouse(Warehouse warehouse);

    /** 单条更新（按 wid） */
    int updateWarehouse(Warehouse warehouse);

    /** 批量插入 */
    int batchInsert(@Param("list") List<Warehouse> list);
}
