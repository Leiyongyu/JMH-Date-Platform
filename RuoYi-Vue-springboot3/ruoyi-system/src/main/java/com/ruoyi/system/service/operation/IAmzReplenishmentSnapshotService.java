package com.ruoyi.system.service.operation;

import java.util.List;
import java.util.Map;

import com.ruoyi.system.domain.operation.AmzSalesBreakdownRequest;
import com.ruoyi.system.domain.operation.AmzReplenishmentSnapshot;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;

public interface IAmzReplenishmentSnapshotService
{
    List<AmzReplenishmentSnapshot> selectAmzReplenishmentSnapshotList(AmzReplenishmentSnapshot snapshot);
    List<AmzReplenishmentSnapshot> search(EbayReplenishmentSearchRequest req);
    List<String> distinctValues(String field, String keyword);
    int refreshSnapshot();
    /** 按仓库SKU查询各店铺销量明细 */
    List<Map<String, Object>> salesBreakdown(String warehouseSku, String field, List<String> storeNames);
    /** 按当前AMZ筛选条件查询各店铺销量明细 */
    List<Map<String, Object>> salesBreakdown(AmzSalesBreakdownRequest req);
}
