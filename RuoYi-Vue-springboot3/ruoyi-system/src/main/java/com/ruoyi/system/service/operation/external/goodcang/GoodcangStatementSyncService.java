package com.ruoyi.system.service.operation.external.goodcang;

import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 领星库存流水同步（后续实现），当前占位 */
@Service
public class GoodcangStatementSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(GoodcangStatementSyncService.class);
    public OperationSyncResult sync() throws Exception
    {
        LOG.info("库存流水同步 - 待实现");
        return OperationSyncResult.success("statement", "领星-库存流水", "erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement", 0, 0, 0);
    }
}
