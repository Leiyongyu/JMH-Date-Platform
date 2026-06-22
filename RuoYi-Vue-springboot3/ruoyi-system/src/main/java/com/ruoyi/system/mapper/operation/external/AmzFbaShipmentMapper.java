package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzFbaShipment;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface AmzFbaShipmentMapper
{
    List<AmzFbaShipment> selectAll();

    /** 检查表是否为空 */
    int count();

    /** 按唯一键 upsert */
    int insert(AmzFbaShipment row);

    /** 批量插入 */
    int batchInsert(@Param("list") List<AmzFbaShipment> list);

    /** 批量 upsert (INSERT ... ON DUPLICATE KEY UPDATE) */
    int batchUpsert(@Param("list") List<AmzFbaShipment> list);
}
