package com.ruoyi.system.service.operation.impl;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;
import com.ruoyi.system.mapper.operation.EbayReplenishmentSnapshotMapper;
import com.ruoyi.system.service.operation.IEbayReplenishmentSnapshotService;
import com.ruoyi.system.service.operation.compute.EbayReplenishmentComputeService;

/** 保留跟价依赖的历史补货量生成；旧页面的搜索、筛选和修改服务已下线。 */
@Service
public class EbayReplenishmentSnapshotServiceImpl implements IEbayReplenishmentSnapshotService
{
    private static final Logger log = LoggerFactory.getLogger(EbayReplenishmentSnapshotServiceImpl.class);
    private final EbayReplenishmentSnapshotMapper snapshotMapper;
    private final EbayReplenishmentComputeService computeService;

    public EbayReplenishmentSnapshotServiceImpl(EbayReplenishmentSnapshotMapper snapshotMapper,
            EbayReplenishmentComputeService computeService)
    {
        this.snapshotMapper = snapshotMapper;
        this.computeService = computeService;
    }

    @Override
    @Transactional
    public int refreshSnapshot()
    {
        long start = System.currentTimeMillis();
        List<EbayReplenishmentSnapshot> computed = computeService.compute();
        if (computed.isEmpty())
        {
            log.warn("跟价补货量计算返回空结果，保留当前快照");
            return 0;
        }
        String batchNo = "EBAY_REPL-" + System.currentTimeMillis();
        for (int i = 0; i < computed.size(); i += 500)
        {
            snapshotMapper.batchInsertSnapshots(computed.subList(i, Math.min(i + 500, computed.size())), batchNo);
        }
        snapshotMapper.activateBatch(batchNo);
        snapshotMapper.deleteNonCurrent();
        log.info("跟价补货量快照刷新完成: {}条, 耗时{}ms", computed.size(), System.currentTimeMillis() - start);
        return computed.size();
    }
}
