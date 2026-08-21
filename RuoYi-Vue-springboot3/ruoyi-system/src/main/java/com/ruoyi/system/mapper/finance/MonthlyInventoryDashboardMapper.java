package com.ruoyi.system.mapper.finance;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** 首页月度库存成本趋势，直接读取Python库已计算完成的DWS汇总表。 */
public interface MonthlyInventoryDashboardMapper
{
    List<Map<String, Object>> selectAvailablePeriods();

    List<Map<String, Object>> selectCostTrend(
            @Param("year") String year,
            @Param("month") String month);
}
