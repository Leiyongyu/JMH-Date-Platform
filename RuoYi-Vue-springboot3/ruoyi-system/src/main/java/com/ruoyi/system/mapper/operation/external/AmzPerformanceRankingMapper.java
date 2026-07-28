package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** Amazon 绩效排名汇总表 Mapper。 */
public interface AmzPerformanceRankingMapper
{
    String selectLatestProfitMonth();

    int deleteByStatMonth(@Param("statMonth") String statMonth);

    int rebuildByStatMonth(@Param("statMonth") String statMonth);

    List<Map<String, Object>> selectList(
            @Param("statMonth") String statMonth,
            @Param("principalName") String principalName);
}
