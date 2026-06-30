package com.ruoyi.system.mapper.operation;

import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

public interface EbayReplenishmentSnapshotMapper
{
    List<EbayReplenishmentSnapshot> selectEbayReplenishmentSnapshotList(EbayReplenishmentSnapshot snapshot);

    List<EbayReplenishmentSnapshot> search(Map<String, Object> params);

    List<String> selectDistinctValues(@Param("column") String column, @Param("keyword") String keyword);

    int insertSnapshot(EbayReplenishmentSnapshot snapshot);

    int batchInsertSnapshots(@Param("list") List<EbayReplenishmentSnapshot> list, @Param("batchNo") String batchNo);

    int deleteAll();

    int activateBatch(@Param("batchNo") String batchNo);

    int deleteNonCurrent();

    int updateProductNature(@Param("id") Long id, @Param("productNature") Integer productNature);
}
