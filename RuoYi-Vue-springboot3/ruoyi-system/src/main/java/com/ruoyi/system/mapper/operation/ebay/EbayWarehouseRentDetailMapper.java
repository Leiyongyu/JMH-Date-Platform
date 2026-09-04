package com.ruoyi.system.mapper.operation.ebay;

import com.ruoyi.system.domain.operation.ebay.EbayWarehouseRentDetail;
import com.ruoyi.system.domain.operation.ebay.EbayWarehouseProductKey;
import java.util.List;
import org.apache.ibatis.annotations.Param;

/** eBay补货2.0仓租源明细持久化。 */
public interface EbayWarehouseRentDetailMapper
{
    /** 锁定单行控制记录，使多Java实例的增量覆盖在数据库层串行。 */
    String lockImport();

    int deleteByOrderNos(@Param("orderNos") List<String> orderNos);

    int deleteByWarehouseProductBillingDays(
            @Param("keys") List<EbayWarehouseProductKey> keys);

    int batchInsert(@Param("items") List<EbayWarehouseRentDetail> items);
}
