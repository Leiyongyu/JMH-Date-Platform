package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** Amazon 月度完整订单利润 Mapper。 */
public interface AmzMonthlyOrderProfitMapper
{
    int deleteByStatMonth(@Param("statMonth") String statMonth);

    int batchUpsert(@Param("list") List<Map<String, Object>> list);

}
