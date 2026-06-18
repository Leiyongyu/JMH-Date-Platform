package com.ruoyi.system.service.operation;

import java.util.List;
import com.ruoyi.system.domain.operation.AmzReplenishmentSnapshot;

public interface IAmzReplenishmentSnapshotService
{
    List<AmzReplenishmentSnapshot> selectAmzReplenishmentSnapshotList(AmzReplenishmentSnapshot snapshot);
}
