package com.ruoyi.system.mapper.operation;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Param;

import com.ruoyi.system.domain.operation.AmzReplenishmentSnapshot;

public interface AmzReplenishmentSnapshotMapper
{
    List<AmzReplenishmentSnapshot> selectAmzReplenishmentSnapshotList(AmzReplenishmentSnapshot snapshot);
    List<AmzReplenishmentSnapshot> search(Map<String, Object> params);
    List<String> selectDistinctValues(@Param("column") String column, @Param("keyword") String keyword);
    int insertByListing();
    int deleteAll();
}
