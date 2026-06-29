package com.ruoyi.system.mapper.operation;

import com.ruoyi.system.domain.operation.AmzReplenishmentSnapshot;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

public interface AmzReplenishmentSnapshotMapper
{
    List<AmzReplenishmentSnapshot> selectAmzReplenishmentSnapshotList(AmzReplenishmentSnapshot snapshot);

    List<AmzReplenishmentSnapshot> search(Map<String, Object> params);

    List<String> selectDistinctValues(@Param("column") String column, @Param("keyword") String keyword);

    /** 按仓库SKU查询各店铺销量明细 */
    List<Map<String, Object>> selectSalesBreakdown(@Param("warehouseSku") String warehouseSku,
                                                    @Param("column") String column,
                                                    @Param("storeNames") List<String> storeNames);

    /** 按当前筛选条件查询各店铺销量明细 */
    List<Map<String, Object>> selectSalesBreakdownByFilters(Map<String, Object> params);

    int insertByListing(@Param("batchNo") String batchNo);

    int deleteAll();

    int activateBatch(@Param("batchNo") String batchNo);

    int deleteNonCurrent();
}
