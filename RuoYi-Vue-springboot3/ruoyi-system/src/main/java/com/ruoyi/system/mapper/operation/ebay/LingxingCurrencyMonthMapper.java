package com.ruoyi.system.mapper.operation.ebay;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** 读取Python同步到date-project库的领星月度汇率。 */
public interface LingxingCurrencyMonthMapper
{
    List<Map<String, Object>> selectRatesByMonth(
            @Param("rateMonth") String rateMonth);
}
