package com.ruoyi.system.mapper.operation.external;

import com.ruoyi.system.domain.operation.external.LingxingShipmentOrderMapping;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface LingxingShipmentOrderMappingMapper
{
    int countAll();

    int batchUpsert(@Param("list") List<LingxingShipmentOrderMapping> list);

    String selectShipmentSnByShipmentId(@Param("shipmentId") String shipmentId);
}
