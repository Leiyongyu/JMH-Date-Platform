package com.ruoyi.system.service.operation.impl;

import java.util.List;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import com.ruoyi.system.domain.operation.AmzReplenishmentSnapshot;
import com.ruoyi.system.mapper.operation.AmzReplenishmentSnapshotMapper;
import com.ruoyi.system.service.operation.IAmzReplenishmentSnapshotService;

@Service
public class AmzReplenishmentSnapshotServiceImpl implements IAmzReplenishmentSnapshotService
{
    private static final Set<String> SORT_FIELDS = Set.of(
        "storeName", "sellerSku", "warehouseSku", "asin", "rating", "reviewCount",
        "adRate", "profitRate30d", "refundRate90d", "domesticStock", "pendingShipQty",
        "fbaStock", "fbaInbound", "totalInventory", "sales7d", "sales14d",
        "sales30d", "sales60d", "avgMonthlySales", "safetyStock", "shipQty",
        "replenishQty", "restockDays"
    );

    @Autowired
    private AmzReplenishmentSnapshotMapper snapshotMapper;

    @Override
    public List<AmzReplenishmentSnapshot> selectAmzReplenishmentSnapshotList(AmzReplenishmentSnapshot snapshot)
    {
        if (snapshot.getSortField() == null || !SORT_FIELDS.contains(snapshot.getSortField()))
        {
            snapshot.setSortField(null);
            snapshot.setSortOrder(null);
        }
        else if (!"ascending".equals(snapshot.getSortOrder()))
        {
            snapshot.setSortOrder("descending");
        }
        return snapshotMapper.selectAmzReplenishmentSnapshotList(snapshot);
    }
}
