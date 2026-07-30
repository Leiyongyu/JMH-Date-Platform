package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** 领星 FBA 库存月度快照数据访问。 */
public interface AmzFbaInventorySnapshotMapper
{
    int deleteByPullMonth(@Param("pullMonth") String pullMonth);

    int batchInsert(@Param("rows") List<Map<String, Object>> rows);

    int countByPullMonth(@Param("pullMonth") String pullMonth);

    String selectLatestPullMonth();

    List<Map<String, Object>> selectList(
            @Param("pullMonth") String pullMonth,
            @Param("warehouseName") String warehouseName,
            @Param("sid") String sid,
            @Param("keyword") String keyword);

    Map<String, Object> selectById(@Param("id") Long id);

    Map<String, Object> selectSummary(@Param("pullMonth") String pullMonth);
}
