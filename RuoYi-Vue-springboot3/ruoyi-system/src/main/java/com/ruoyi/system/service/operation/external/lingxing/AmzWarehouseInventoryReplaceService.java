package com.ruoyi.system.service.operation.external.lingxing;

import com.ruoyi.system.domain.operation.external.AmzWarehouseInventoryDetail;
import com.ruoyi.system.mapper.operation.external.AmzWarehouseInventoryDetailMapper;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** 在领星数据完整拉取、合并并校验后，使用短事务原子替换 Amazon 仓库库存明细。 */
@Service
public class AmzWarehouseInventoryReplaceService
{
    private static final int INSERT_BATCH_SIZE = 1000;

    private final AmzWarehouseInventoryDetailMapper mapper;

    public AmzWarehouseInventoryReplaceService(AmzWarehouseInventoryDetailMapper mapper)
    {
        this.mapper = mapper;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW, rollbackFor = Exception.class)
    public int replaceAll(List<AmzWarehouseInventoryDetail> rows)
    {
        if (rows == null || rows.isEmpty())
        {
            throw new IllegalArgumentException("AMZ仓库库存明细替换数据不能为空");
        }

        mapper.deleteAll();
        int inserted = 0;
        for (int from = 0; from < rows.size(); from += INSERT_BATCH_SIZE)
        {
            int to = Math.min(from + INSERT_BATCH_SIZE, rows.size());
            List<AmzWarehouseInventoryDetail> batch =
                    new ArrayList<>(rows.subList(from, to));
            inserted += mapper.batchInsert(batch);
        }
        if (inserted != rows.size())
        {
            throw new IllegalStateException("AMZ仓库库存明细写入数量不一致，期望"
                    + rows.size() + "条，实际" + inserted + "条");
        }
        return inserted;
    }
}
