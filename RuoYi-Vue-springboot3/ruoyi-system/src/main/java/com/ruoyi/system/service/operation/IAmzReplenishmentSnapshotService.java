package com.ruoyi.system.service.operation;

import java.util.List;

import com.ruoyi.system.domain.operation.AmzReplenishmentSnapshot;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;

public interface IAmzReplenishmentSnapshotService
{
    List<AmzReplenishmentSnapshot> selectAmzReplenishmentSnapshotList(AmzReplenishmentSnapshot snapshot);
    List<AmzReplenishmentSnapshot> search(EbayReplenishmentSearchRequest req);
    List<String> distinctValues(String field, String keyword);
    void refreshSnapshot();
}
