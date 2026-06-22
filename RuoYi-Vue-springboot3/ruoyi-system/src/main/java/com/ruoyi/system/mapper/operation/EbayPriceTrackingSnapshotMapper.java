package com.ruoyi.system.mapper.operation;

import com.ruoyi.system.domain.operation.EbayPriceTrackingSnapshot;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

public interface EbayPriceTrackingSnapshotMapper
{
    List<EbayPriceTrackingSnapshot> search(Map<String, Object> params);

    List<String> selectDistinctValues(@Param("column") String column, @Param("keyword") String keyword);

    int batchInsert(@Param("list") List<EbayPriceTrackingSnapshot> list, @Param("batchNo") String batchNo);

    int deleteAll();

    int activateBatch(@Param("batchNo") String batchNo);

    int deleteNonCurrent();

    int fillReplenishQtyFromSnapshot();
}
