package com.ruoyi.system.service.operation.impl;

import java.util.List;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;
import com.ruoyi.system.mapper.operation.EbayReplenishmentSnapshotMapper;
import com.ruoyi.system.service.operation.IEbayReplenishmentSnapshotService;

@Service
public class EbayReplenishmentSnapshotServiceImpl implements IEbayReplenishmentSnapshotService
{
    private static final Set<String> SORT_FIELDS = Set.of(
        "site", "sku", "skuLevel", "profitRate30d", "returnRate",
        "overseasSellable", "overseasTotal", "totalInventory",
        "sales7d", "sales30d", "sales90d", "maxMonthlySales",
        "suggestPurchaseQty", "maxMonthlyReplenishQty"
    );

    @Autowired
    private EbayReplenishmentSnapshotMapper snapshotMapper;

    @Override
    public List<EbayReplenishmentSnapshot> selectEbayReplenishmentSnapshotList(EbayReplenishmentSnapshot snapshot)
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
        return snapshotMapper.selectEbayReplenishmentSnapshotList(snapshot);
    }
}
