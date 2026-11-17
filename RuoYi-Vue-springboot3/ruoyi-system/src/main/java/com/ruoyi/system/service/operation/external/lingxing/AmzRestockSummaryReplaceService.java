package com.ruoyi.system.service.operation.external.lingxing;

import com.ruoyi.system.domain.operation.external.AmzRestockSummary;
import com.ruoyi.system.mapper.operation.external.AmzRestockSummaryMapper;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** Publish only fully collected replenishment results, in one short transaction. */
@Service
public class AmzRestockSummaryReplaceService
{
    private final AmzRestockSummaryMapper mapper;

    public AmzRestockSummaryReplaceService(AmzRestockSummaryMapper mapper) { this.mapper = mapper; }

    @Transactional(propagation = Propagation.REQUIRES_NEW, rollbackFor = Exception.class)
    public int replaceAll(List<AmzRestockSummary> rows)
    {
        if (rows == null || rows.isEmpty())
            throw new IllegalArgumentException("Amazon补货建议全量结果为空，保留原数据");
        checkCancelled();
        mapper.deleteAll();
        int inserted = 0;
        for (int from = 0; from < rows.size(); from += 500)
        {
            checkCancelled();
            inserted += mapper.batchInsert(new ArrayList<>(rows.subList(from, Math.min(from + 500, rows.size()))));
        }
        checkCancelled();
        if (inserted != rows.size())
            throw new IllegalStateException("Amazon补货建议写入数量不一致，已回滚：期望" + rows.size() + "，实际" + inserted);
        return inserted;
    }

    static void checkCancelled()
    {
        if (Thread.currentThread().isInterrupted())
            throw new IllegalStateException("Amazon补货建议任务已取消，保留原数据");
    }
}
