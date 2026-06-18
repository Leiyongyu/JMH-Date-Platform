package com.ruoyi.system.mapper.operation;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Param;

import com.ruoyi.system.domain.operation.EbayPriceTrackingSnapshot;

public interface EbayPriceTrackingSnapshotMapper
{
    /** SQL下推搜索 */
    List<EbayPriceTrackingSnapshot> search(Map<String, Object> params);

    /** distinct候选值 */
    List<String> selectDistinctValues(@Param("column") String column, @Param("keyword") String keyword);

    /** 批量插入 */
    int batchInsert(List<EbayPriceTrackingSnapshot> list);

    /** 清空表 */
    int deleteAll();
}
