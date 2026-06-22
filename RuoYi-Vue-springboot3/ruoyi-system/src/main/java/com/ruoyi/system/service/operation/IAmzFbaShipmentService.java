package com.ruoyi.system.service.operation;

import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.external.AmzFbaShipment;
import java.util.List;

public interface IAmzFbaShipmentService
{
    List<AmzFbaShipment> search(EbayReplenishmentSearchRequest req);
}
