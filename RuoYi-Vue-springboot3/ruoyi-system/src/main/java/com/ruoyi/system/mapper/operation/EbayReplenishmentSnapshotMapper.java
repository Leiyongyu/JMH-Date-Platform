package com.ruoyi.system.mapper.operation;

import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface EbayReplenishmentSnapshotMapper
{
    List<EbayReplenishmentSnapshot> selectEbayReplenishmentSnapshotList(EbayReplenishmentSnapshot snapshot);

    int batchInsertSnapshots(@Param("list") List<EbayReplenishmentSnapshot> list, @Param("batchNo") String batchNo);

    int activateBatch(@Param("batchNo") String batchNo);

    int deleteNonCurrent();

}
