package com.ruoyi.system.service.operation.sync;

import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import org.springframework.stereotype.Service;

/** 旧报关产品库任务保留为兼容入口；商品资料改为页面按需匹配，不再定时写库。 */
@Service
public class CustomsProductSyncService
{
    public OperationSyncResult sync()
    {
        return OperationSyncResult.skipped("customs_product", "报关产品库同步", "manual/match",
                "已改为报关单页面按单号实时匹配，无需定时同步", 0L);
    }
}
