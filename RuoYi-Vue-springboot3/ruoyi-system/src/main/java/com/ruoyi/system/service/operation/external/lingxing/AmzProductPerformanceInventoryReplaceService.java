package com.ruoyi.system.service.operation.external.lingxing;

import com.ruoyi.system.domain.operation.external.AmzProductPerformanceInventory;
import com.ruoyi.system.mapper.operation.external.AmzProductPerformanceInventoryMapper;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** 在数据完整拉取并校验通过后，使用短事务原子替换产品表现库存。 */
@Service
public class AmzProductPerformanceInventoryReplaceService
{
    private static final int INSERT_BATCH_SIZE = 1000;

    private final AmzProductPerformanceInventoryMapper mapper;

    public AmzProductPerformanceInventoryReplaceService(AmzProductPerformanceInventoryMapper mapper)
    {
        this.mapper = mapper;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW, rollbackFor = Exception.class)
    public int replaceAll(List<AmzProductPerformanceInventory> rows)
    {
        if (rows == null || rows.isEmpty())
        {
            throw new IllegalArgumentException("AMZ产品表现库存替换数据不能为空");
        }

        mapper.deleteAll();
        int inserted = 0;
        for (int from = 0; from < rows.size(); from += INSERT_BATCH_SIZE)
        {
            int to = Math.min(from + INSERT_BATCH_SIZE, rows.size());
            List<AmzProductPerformanceInventory> batch = new ArrayList<>(rows.subList(from, to));
            inserted += mapper.batchInsert(batch);
        }
        if (inserted != rows.size())
        {
            throw new IllegalStateException("AMZ产品表现库存写入数量不一致，期望"
                    + rows.size() + "条，实际" + inserted + "条");
        }
        return inserted;
    }
}
