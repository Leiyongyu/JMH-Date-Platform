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

    int insertByListing(@Param("batchNo") String batchNo);

    int deleteAll();

    int activateBatch(@Param("batchNo") String batchNo);

    int deleteNonCurrent();
}
