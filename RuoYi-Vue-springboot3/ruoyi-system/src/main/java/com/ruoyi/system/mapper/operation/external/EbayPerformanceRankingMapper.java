package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** eBay 月度绩效排名 Mapper。 */
public interface EbayPerformanceRankingMapper
{
    String selectLatestProfitMonth();

    int deleteByStatMonth(@Param("statMonth") String statMonth);

    int rebuildByStatMonth(@Param("statMonth") String statMonth);

    int countProfitRows(@Param("statMonth") String statMonth);

    int countUnmatchedProfitRows(@Param("statMonth") String statMonth);

    int countOwnerRules(@Param("statMonth") String statMonth);

    List<Map<String, Object>> selectList(
            @Param("statMonth") String statMonth,
            @Param("principalName") String principalName);
}
