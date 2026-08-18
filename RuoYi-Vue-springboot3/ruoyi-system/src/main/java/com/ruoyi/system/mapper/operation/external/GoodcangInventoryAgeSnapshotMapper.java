package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** 谷仓库存库龄月度原始快照Mapper。 */
public interface GoodcangInventoryAgeSnapshotMapper
{
    int deleteBySnapshotMonth(@Param("snapshotMonth") String snapshotMonth);

    int batchInsert(@Param("list") List<Map<String, Object>> list);
}
