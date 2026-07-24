package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.AmzOrderProfit;
import java.util.Date;
import java.util.List;
import org.apache.ibatis.annotations.Param;

/** Amazon 最近90天 MSKU 利润率。 */
public interface AmzOrderProfit90dMapper
{
    int batchUpsert(@Param("list") List<AmzOrderProfit> list);

    int deleteNotSyncedSince(@Param("syncStartedAt") Date syncStartedAt);
}
