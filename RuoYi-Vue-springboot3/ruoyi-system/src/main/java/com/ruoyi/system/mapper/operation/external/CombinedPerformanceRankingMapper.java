package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** AMZ 与 eBay 统一绩效排名。 */
public interface CombinedPerformanceRankingMapper
{
    String selectLatestSourceMonth();

    int countAmzProfitRows(@Param("statMonth") String statMonth);

    int countEbayProfitRows(@Param("statMonth") String statMonth);

    int deleteByStatMonth(@Param("statMonth") String statMonth);

    int rebuildByStatMonth(@Param("statMonth") String statMonth);

    List<Map<String, Object>> selectList(
            @Param("statMonth") String statMonth,
            @Param("principalName") String principalName);
}
