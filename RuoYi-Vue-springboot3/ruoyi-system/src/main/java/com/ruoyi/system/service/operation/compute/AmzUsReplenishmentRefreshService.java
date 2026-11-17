package com.ruoyi.system.service.operation.compute;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import com.ruoyi.system.mapper.operation.AmzReplenishmentSnapshotMapper;

/** 美国组补货快照生成、批次激活与旧批次清理。 */
@Service
public class AmzUsReplenishmentRefreshService
{
    private final AmzReplenishmentSnapshotMapper mapper;

    public AmzUsReplenishmentRefreshService(AmzReplenishmentSnapshotMapper mapper)
    {
        this.mapper = mapper;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public int refresh(String batchNo)
    {
        int rows = mapper.insertUsByListing(batchNo);
        if (rows <= 0) throw new IllegalStateException("AMZ美国组快照生成结果为空，已保留原快照");
        mapper.updateUsProfitRate90d(batchNo);
        mapper.activateUsBatch(batchNo);
        mapper.deleteUsNonCurrent();
        return rows;
    }
}
