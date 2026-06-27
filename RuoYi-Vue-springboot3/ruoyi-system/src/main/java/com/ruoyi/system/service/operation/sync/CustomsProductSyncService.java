package com.ruoyi.system.service.operation.sync;

import com.ruoyi.system.mapper.operation.customs.CustomsProductMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 报关产品库同步：备货单详情 + FBA装箱明细 + 出入库清单 → customs_products_list */
@Service
public class CustomsProductSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(CustomsProductSyncService.class);
    private final CustomsProductMapper mapper;

    public CustomsProductSyncService(CustomsProductMapper mapper)
    { this.mapper = mapper; }

    public OperationSyncResult sync() throws Exception
    {
        long start = System.currentTimeMillis();
        int beforeCount = mapper.countAll();
        int overseasRows = mapper.refreshFromJoin();
        int amzRows = mapper.insertMissingFromAmzShipmentBox();
        int afterCount = mapper.countAll();
        int insertedRows = Math.max(afterCount - beforeCount, 0);
        int affectedRows = overseasRows + amzRows;
        LOG.info("报关产品库同步完成: SQL影响{}条(备货单{}, AMZ装箱{}), 实际新增{}条, 当前商品库{}条",
                affectedRows, overseasRows, amzRows, insertedRows, afterCount);
        return OperationSyncResult.success("customs_product", "报关产品库同步", "sql/join",
                afterCount, insertedRows, System.currentTimeMillis() - start);
    }
}
