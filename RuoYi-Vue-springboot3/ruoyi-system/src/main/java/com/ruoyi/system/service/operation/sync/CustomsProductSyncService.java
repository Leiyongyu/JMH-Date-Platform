package com.ruoyi.system.service.operation.sync;

import com.ruoyi.system.mapper.operation.customs.CustomsProductMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 报关产品库同步：overseas_stock_order_detail + customs_inventory_list → customs_products_list */
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
        int rows = mapper.refreshFromJoin();
        LOG.info("报关产品库同步完成: {} 条", rows);
        return OperationSyncResult.success("customs_product", "报关产品库同步", "sql/join", rows, rows, System.currentTimeMillis() - start);
    }
}
