package com.ruoyi.system.service.operation.external.lingxing;

import com.ruoyi.system.mapper.operation.external.AmzFbaInventorySnapshotMapper;
import com.ruoyi.system.mapper.operation.external.AmzFbaInventoryAgeGroupSummaryMapper;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 在单个事务内整月替换 FBA 库存快照。 */
@Service
public class AmzFbaInventorySnapshotReplaceService
{
    private static final int DB_BATCH_SIZE = 50;

    private final AmzFbaInventorySnapshotMapper mapper;
    private final AmzFbaInventoryAgeGroupSummaryMapper summaryMapper;

    public AmzFbaInventorySnapshotReplaceService(
            AmzFbaInventorySnapshotMapper mapper,
            AmzFbaInventoryAgeGroupSummaryMapper summaryMapper)
    {
        this.mapper = mapper;
        this.summaryMapper = summaryMapper;
    }

    @Transactional(rollbackFor = Exception.class)
    public int replaceMonth(String pullMonth, List<Map<String, Object>> rows)
    {
        if (rows == null || rows.isEmpty())
            throw new IllegalArgumentException("FBA库存快照不能为空，拒绝覆盖原月份数据");

        mapper.deleteByPullMonth(pullMonth);
        int inserted = 0;
        for (int i = 0; i < rows.size(); i += DB_BATCH_SIZE)
        {
            inserted += mapper.batchInsert(
                    rows.subList(i, Math.min(i + DB_BATCH_SIZE, rows.size())));
        }
        if (inserted != rows.size())
            throw new IllegalStateException("FBA库存快照写入不完整：应写入"
                    + rows.size() + "条，实际写入" + inserted + "条");

        summaryMapper.deleteByPullMonth(pullMonth);
        int groupCount = summaryMapper.insertFromSnapshot(pullMonth);
        if (groupCount <= 0)
            throw new IllegalStateException(
                    "FBA库存库龄分组汇总结果为空，已回滚本月快照");
        return inserted;
    }
}
