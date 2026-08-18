package com.ruoyi.system.mapper.operation.external;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** 领星产品管理采购价与头程成本月度原始快照Mapper。 */
public interface LingxingProductProcurementSnapshotMapper
{
    int deleteStepPricesBySnapshotMonth(
            @Param("snapshotMonth") String snapshotMonth);

    int deleteTransportCostsBySnapshotMonth(
            @Param("snapshotMonth") String snapshotMonth);

    int deleteProductsBySnapshotMonth(
            @Param("snapshotMonth") String snapshotMonth);

    int batchInsertProducts(@Param("list") List<Map<String, Object>> list);

    int batchInsertStepPrices(@Param("list") List<Map<String, Object>> list);

    int batchInsertTransportCosts(
            @Param("list") List<Map<String, Object>> list);
}
