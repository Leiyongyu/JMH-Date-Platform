package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** Amazon FBA 库龄组别最终汇总表数据访问。 */
public interface AmzFbaInventoryAgeGroupSummaryMapper
{
    int deleteByPullMonth(@Param("pullMonth") String pullMonth);

    int insertFromSnapshot(@Param("pullMonth") String pullMonth);

    String selectLatestPullMonth();

    List<Map<String, Object>> selectList(
            @Param("pullMonth") String pullMonth);

    Map<String, Object> selectSummary(
            @Param("pullMonth") String pullMonth);
}
