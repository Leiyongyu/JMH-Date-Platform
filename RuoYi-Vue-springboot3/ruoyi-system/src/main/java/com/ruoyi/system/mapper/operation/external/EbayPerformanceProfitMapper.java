package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.EbayPerformanceProfit;
import java.util.List;
import org.apache.ibatis.annotations.Param;

/** eBay 月度绩效利润明细 Mapper。 */
public interface EbayPerformanceProfitMapper
{
    int deleteByStatMonth(@Param("statMonth") String statMonth);

    int insertBatch(@Param("rows") List<EbayPerformanceProfit> rows);
}
